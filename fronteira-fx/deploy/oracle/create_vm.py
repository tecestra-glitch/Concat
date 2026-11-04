"""Cria (ou reaproveita) a VM Always Free do coletor na Oracle Cloud pela API, com o cloud-init do projeto.

Uso (fora do repositório, com o SDK oficial `oci` instalado num ambiente isolado):

    python -I create_vm.py --config ~/.oci/config --cloud-init cloud-init.yaml --ssh-pubkey id_ed25519.pub

Idempotente: reaproveita a VCN, a sub-rede e a instância com os nomes abaixo. A VCN não libera nenhuma porta de
entrada (o coletor só sai para a internet). Tenta VM.Standard.A1.Flex (1 OCPU, 6 GB) em cada domínio de
disponibilidade e, se faltar capacidade em todos, VM.Standard.E2.1.Micro. Nada aqui imprime o conteúdo do cloud-init
(ele tem a senha do papel fx_worker).
"""

from __future__ import annotations

import argparse
import base64
import sys
import time

import oci

VCN_NAME = "fronteira-fx-vcn"
SUBNET_NAME = "fronteira-fx-publica"
INSTANCE_NAME = "fronteira-fx-coletor"
SHAPES = [
    ("VM.Standard.A1.Flex", {"ocpus": 1.0, "memory_in_gbs": 6.0}),
    ("VM.Standard.E2.1.Micro", None),
]


def log(msg: str) -> None:
    print(f"[oracle] {msg}", flush=True)


def wait_state(get, ident: str, states: set[str], timeout_s: int = 600) -> object:
    deadline = time.monotonic() + timeout_s
    while True:
        obj = get(ident).data
        if obj.lifecycle_state in states:
            return obj
        if time.monotonic() > deadline:
            raise TimeoutError(f"{ident} ficou em {obj.lifecycle_state}")
        time.sleep(5)


def ensure_network(vn: oci.core.VirtualNetworkClient, compartment: str) -> str:
    vcns = [v for v in vn.list_vcns(compartment).data if v.display_name == VCN_NAME and v.lifecycle_state == "AVAILABLE"]
    if vcns:
        vcn = vcns[0]
        log(f"VCN existente {vcn.id[-12:]}")
    else:
        vcn = vn.create_vcn(oci.core.models.CreateVcnDetails(
            compartment_id=compartment, display_name=VCN_NAME, cidr_blocks=["10.42.0.0/16"], dns_label="fxvcn")).data
        vcn = wait_state(vn.get_vcn, vcn.id, {"AVAILABLE"})
        log("VCN criada")
    igws = [g for g in vn.list_internet_gateways(compartment, vcn_id=vcn.id).data if g.lifecycle_state == "AVAILABLE"]
    igw = igws[0] if igws else vn.create_internet_gateway(oci.core.models.CreateInternetGatewayDetails(
        compartment_id=compartment, vcn_id=vcn.id, display_name="fronteira-fx-igw", is_enabled=True)).data
    vn.update_route_table(vcn.default_route_table_id, oci.core.models.UpdateRouteTableDetails(route_rules=[
        oci.core.models.RouteRule(destination="0.0.0.0/0", destination_type="CIDR_BLOCK", network_entity_id=igw.id)]))
    # Só saída: nenhuma regra de entrada (nem SSH). O console serial da Oracle continua disponível para emergência.
    vn.update_security_list(vcn.default_security_list_id, oci.core.models.UpdateSecurityListDetails(
        ingress_security_rules=[],
        egress_security_rules=[oci.core.models.EgressSecurityRule(destination="0.0.0.0/0", protocol="all")]))
    subnets = [s for s in vn.list_subnets(compartment, vcn_id=vcn.id).data
               if s.display_name == SUBNET_NAME and s.lifecycle_state == "AVAILABLE"]
    if subnets:
        return subnets[0].id
    sn = vn.create_subnet(oci.core.models.CreateSubnetDetails(
        compartment_id=compartment, vcn_id=vcn.id, display_name=SUBNET_NAME, cidr_block="10.42.1.0/24",
        dns_label="publica", prohibit_public_ip_on_vnic=False)).data
    wait_state(vn.get_subnet, sn.id, {"AVAILABLE"})
    log("sub-rede criada")
    return sn.id


def ubuntu_image(compute: oci.core.ComputeClient, compartment: str, shape: str) -> str:
    images = compute.list_images(compartment, operating_system="Canonical Ubuntu", operating_system_version="24.04",
                                 shape=shape, sort_by="TIMECREATED", sort_order="DESC").data
    images = [i for i in images if "Minimal" not in (i.display_name or "")] or images
    if not images:
        raise RuntimeError(f"nenhuma imagem Ubuntu 24.04 para {shape}")
    return images[0].id


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--profile", default="DEFAULT")
    ap.add_argument("--cloud-init", required=True)
    ap.add_argument("--ssh-pubkey", required=True)
    args = ap.parse_args(argv)

    config = oci.config.from_file(args.config, args.profile)
    oci.config.validate_config(config)
    tenancy = config["tenancy"]
    identity = oci.identity.IdentityClient(config)
    compute = oci.core.ComputeClient(config)
    vn = oci.core.VirtualNetworkClient(config)

    existing = [i for i in compute.list_instances(tenancy, display_name=INSTANCE_NAME).data
                if i.lifecycle_state not in ("TERMINATED", "TERMINATING")]
    if existing:
        log(f"instância já existe: {existing[0].lifecycle_state} ({existing[0].shape})")
        return 0

    subnet_id = ensure_network(vn, tenancy)
    user_data = base64.b64encode(open(args.cloud_init, "rb").read()).decode()
    ssh_key = open(args.ssh_pubkey).read().strip()
    ads = [ad.name for ad in identity.list_availability_domains(tenancy).data]
    log(f"domínios de disponibilidade: {len(ads)}")

    for shape, shape_config in SHAPES:
        image_id = ubuntu_image(compute, tenancy, shape)
        for ad in ads:
            details = oci.core.models.LaunchInstanceDetails(
                compartment_id=tenancy, availability_domain=ad, display_name=INSTANCE_NAME, shape=shape,
                shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(**shape_config) if shape_config else None,
                source_details=oci.core.models.InstanceSourceViaImageDetails(image_id=image_id, boot_volume_size_in_gbs=50),
                create_vnic_details=oci.core.models.CreateVnicDetails(subnet_id=subnet_id, assign_public_ip=True),
                metadata={"user_data": user_data, "ssh_authorized_keys": ssh_key},
            )
            try:
                inst = compute.launch_instance(details).data
            except oci.exceptions.ServiceError as exc:
                text = f"{exc.code}: {exc.message}"
                if "capacity" in text.lower() or exc.status in (429, 500):
                    log(f"{shape} sem capacidade em {ad[-6:]} ({exc.code})")
                    continue
                if "LimitExceeded" in text or "limit" in text.lower():
                    log(f"{shape}: limite da conta ({exc.code}); tentando a próxima forma")
                    break
                raise
            log(f"lançada {shape} em {ad[-6:]}; esperando RUNNING")
            inst = wait_state(compute.get_instance, inst.id, {"RUNNING", "TERMINATED"}, timeout_s=900)
            log(f"estado: {inst.lifecycle_state}")
            return 0 if inst.lifecycle_state == "RUNNING" else 1
    log("nenhuma forma Always Free com capacidade agora; tente de novo mais tarde")
    return 2


if __name__ == "__main__":
    sys.exit(main())
