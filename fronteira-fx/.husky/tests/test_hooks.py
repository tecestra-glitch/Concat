#!/usr/bin/env python3
"""Testes dos hooks do husky (fronteira-fx/.husky/pre-commit e pre-push).

Cada teste monta um repositório Git temporário com `fronteira-fx/` e uma pasta
"Rust" ao lado, copia os hooks para dentro dele e os executa como o husky faz
(`sh -e <hook>`), com ferramentas falsas no PATH (trufflehog, docker, pnpm, uv)
que registram os argumentos recebidos e saem com o código pedido por variável
de ambiente. Nenhuma rede, nenhum pnpm/uv de verdade.

Uso (da raiz do repositório ou de qualquer pasta):

    python3 -I fronteira-fx/.husky/tests/test_hooks.py

Só precisa de `git` e de um `sh` POSIX no PATH.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HUSKY_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = HUSKY_DIR.parents[1]
SECRET_SCAN_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "secret-scan.yml"
HOOK_FILES = ("pre-commit", "pre-push", "scan-secrets.sh")
ZERO_SHA = "0" * 40


def pinned_version(path: Path, pattern: str) -> str:
    """Primeiro grupo de `pattern` na primeira linha de `path` que casa; falha se não houver."""
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(pattern, line)
        if m:
            return m.group(1)
    raise AssertionError(f"{path}: nenhuma linha casa com {pattern!r}")


# A versão dos hooks vem do próprio scan-secrets.sh; a da CI, do input `version` em secret-scan.yml.
HOOKS_VERSION = pinned_version(HUSKY_DIR / "scan-secrets.sh", r'^TRUFFLEHOG_VERSION="([^"]+)"$')

FAKE_TOOLS = {
    # `--version` responde com FAKE_TRUFFLEHOG_VERSION; FAKE_TRUFFLEHOG_EAT_STDIN=1 consome o stdin (com o
    # builtin `read`, porque o PATH dos testes não tem `cat`), como faria uma ferramenta que lê a entrada.
    # Imprime algo em stderr para o teste conferir que a saída do TruffleHog não vai para /dev/null.
    "trufflehog": (
        '#!/bin/sh\necho "trufflehog $*" >> "$FAKE_LOG"\n'
        'if [ "$1" = "--version" ]; then echo "trufflehog ${FAKE_TRUFFLEHOG_VERSION}"; exit 0; fi\n'
        'if [ "${FAKE_TRUFFLEHOG_EAT_STDIN:-0}" = "1" ]; then while read -r _l; do :; done; fi\n'
        'echo "TRUFFLEHOG-SAIDA-VISIVEL" >&2\nexit "${FAKE_TRUFFLEHOG_RC:-0}"\n'
    ),
    # `docker info` responde conforme FAKE_DOCKER_INFO_RC; `docker run` imita o TruffleHog na imagem.
    "docker": (
        '#!/bin/sh\necho "docker $*" >> "$FAKE_LOG"\n'
        'case "$1" in\n'
        '  info) exit "${FAKE_DOCKER_INFO_RC:-1}" ;;\n'
        '  run) echo "TRUFFLEHOG-DOCKER-SAIDA-VISIVEL" >&2; exit "${FAKE_TRUFFLEHOG_RC:-0}" ;;\n'
        "esac\nexit 0\n"
    ),
    "pnpm": '#!/bin/sh\necho "pnpm $*" >> "$FAKE_LOG"\nexit "${FAKE_PNPM_RC:-0}"\n',
    "uv": '#!/bin/sh\necho "uv $*" >> "$FAKE_LOG"\nexit "${FAKE_UV_RC:-0}"\n',
}


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class HookRepo:
    """Repositório temporário com os hooks copiados e ferramentas falsas no PATH."""

    def __init__(self, root: Path, *, with_trufflehog: bool = True) -> None:
        self.root = root
        self.repo = root / "repo"
        self.bin = root / "bin"
        self.log = root / "calls.log"
        self.bin.mkdir()
        self.log.touch()
        for name, body in FAKE_TOOLS.items():
            if name == "trufflehog" and not with_trufflehog:
                continue
            _write_executable(self.bin / name, body)
        # PATH mínimo: ferramentas falsas + só `git` e `sh` de verdade. Assim um
        # trufflehog instalado na máquina de quem roda o teste não interfere.
        sysbin = root / "sys"
        sysbin.mkdir()
        for tool in ("git", "sh"):
            real = shutil.which(tool)
            if real is None:
                raise RuntimeError(f"{tool} não encontrado no PATH")
            os.symlink(real, sysbin / tool)
        self.path = f"{self.bin}{os.pathsep}{sysbin}"

        self.repo.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "hooks@example.invalid")
        self.git("config", "user.name", "Hooks Test")
        self.git("config", "commit.gpgsign", "false")
        hooks = self.repo / "fronteira-fx" / ".husky"
        hooks.mkdir(parents=True)
        for name in HOOK_FILES:
            shutil.copy(HUSKY_DIR / name, hooks / name)
        (self.repo / "fronteira-fx" / "package.json").write_text('{"name":"fx"}\n', encoding="utf-8")
        self.write("src/main.rs", "fn main() {}\n")
        self.write("fronteira-fx/src/app.ts", "export const a = 1;\n")
        self.write("fronteira-fx/backend/src/fx.py", "A = 1\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "inicial")
        self.base_sha = self.rev("HEAD")

    def write(self, rel: str, text: str) -> None:
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def git(self, *args: str) -> str:
        env = {**os.environ, "PATH": self.path, "GIT_CONFIG_NOSYSTEM": "1", "HOME": str(self.root)}
        return subprocess.run(
            ["git", *args], cwd=self.repo, env=env, check=True, capture_output=True, text=True
        ).stdout.strip()

    def rev(self, ref: str) -> str:
        return self.git("rev-parse", ref)

    def commit(self, rel: str, text: str, msg: str) -> str:
        self.write(rel, text)
        self.git("add", rel)
        self.git("commit", "-q", "-m", msg)
        return self.rev("HEAD")

    def run_hook(
        self,
        name: str,
        *,
        env: dict[str, str] | None = None,
        stdin: str = "",
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        full_env = {
            "PATH": self.path,
            "HOME": str(self.root),
            "GIT_CONFIG_NOSYSTEM": "1",
            "FAKE_LOG": str(self.log),
            "FAKE_TRUFFLEHOG_VERSION": HOOKS_VERSION,
            "LC_ALL": "C",
        }
        if env:
            full_env.update(env)
        # Igual ao husky 9 (`_/h`): `sh -e <hook> <args>`, a partir da raiz do repositório.
        args = ["origin", "file:///remoto"] if name == "pre-push" else []
        return subprocess.run(
            ["sh", "-e", f"fronteira-fx/.husky/{name}", *args],
            cwd=cwd or self.repo,
            env=full_env,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def calls(self) -> list[str]:
        return [line for line in self.log.read_text(encoding="utf-8").splitlines() if line]


class HookTestCase(unittest.TestCase):
    with_trufflehog = True

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="fx-hooks-")
        self.addCleanup(self._tmp.cleanup)
        self.r = HookRepo(Path(self._tmp.name), with_trufflehog=self.with_trufflehog)

    def assertCalled(self, prefix: str) -> str:
        for line in self.r.calls():
            if line.startswith(prefix):
                return line
        self.fail(f"esperava chamada começando com {prefix!r}; chamadas: {self.r.calls()}")

    def assertNotCalled(self, prefix: str) -> None:
        hits = [line for line in self.r.calls() if line.startswith(prefix)]
        self.assertEqual(hits, [], f"não esperava chamada {prefix!r}")


class ArquivosDosHooks(unittest.TestCase):
    def test_hooks_sao_executaveis_e_tem_sintaxe_valida(self) -> None:
        for name in ("pre-commit", "pre-push"):
            path = HUSKY_DIR / name
            self.assertTrue(os.access(path, os.X_OK), f"{name} precisa ser executável (chmod +x)")
            subprocess.run(["sh", "-n", str(path)], check=True)
        subprocess.run(["sh", "-n", str(HUSKY_DIR / "scan-secrets.sh")], check=True)

    def test_hooks_usam_set_e_e_nao_escondem_saida(self) -> None:
        for name in ("pre-commit", "pre-push", "scan-secrets.sh"):
            text = (HUSKY_DIR / name).read_text(encoding="utf-8")
            self.assertNotIn(":latest", text, f"{name}: imagem do TruffleHog deve ter versão fixa")
            # Só as sondagens (`command -v`, `docker info`) podem ser silenciadas; a varredura, não.
            for line in text.splitlines():
                if "command -v" in line or "docker info" in line:
                    continue
                if "/dev/null" in line and "trufflehog" in line:
                    self.fail(f"{name}: saída do TruffleHog redirecionada para /dev/null: {line.strip()}")
        for name in ("pre-commit", "pre-push"):
            self.assertIn("set -e", (HUSKY_DIR / name).read_text(encoding="utf-8"), f"{name} precisa de set -e")

    def test_versao_do_trufflehog_e_a_mesma_da_ci(self) -> None:
        ci_version = pinned_version(SECRET_SCAN_WORKFLOW, r'^\s*version: "([^"]+)"$')
        self.assertEqual(
            HOOKS_VERSION,
            ci_version,
            "TRUFFLEHOG_VERSION em scan-secrets.sh e o input `version` em .github/workflows/secret-scan.yml devem ser iguais",
        )


class PreCommit(HookTestCase):
    def test_segredo_verificado_bloqueia_com_mensagem_e_sem_lint(self) -> None:
        self.r.write("fronteira-fx/src/app.ts", "export const a = 2;\n")
        self.r.git("add", "fronteira-fx/src/app.ts")
        res = self.r.run_hook("pre-commit", env={"FAKE_TRUFFLEHOG_RC": "183"})
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Commit bloqueado", res.stdout + res.stderr)
        self.assertIn("TRUFFLEHOG-SAIDA-VISIVEL", res.stderr, "a saída do TruffleHog deve aparecer")
        self.assertNotCalled("pnpm")

    def test_erro_da_ferramenta_avisa_e_nao_bloqueia(self) -> None:
        self.r.write("fronteira-fx/src/app.ts", "export const a = 2;\n")
        self.r.git("add", "fronteira-fx/src/app.ts")
        res = self.r.run_hook("pre-commit", env={"FAKE_TRUFFLEHOG_RC": "1"})
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("aviso", res.stdout + res.stderr)
        self.assertCalled("pnpm exec lint-staged")

    def test_varredura_limpa_roda_lint_staged_e_vitest_rapido(self) -> None:
        self.r.write("fronteira-fx/src/app.ts", "export const a = 2;\n")
        self.r.git("add", "fronteira-fx/src/app.ts")
        res = self.r.run_hook("pre-commit")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        scan = self.assertCalled("trufflehog git")
        self.assertIn("--only-verified", scan)
        self.assertIn("--fail", scan)
        self.assertIn("--since-commit HEAD", scan)
        self.assertCalled("pnpm exec lint-staged")
        vitest = self.assertCalled("pnpm exec vitest run")
        self.assertIn("--changed", vitest)

    def test_commit_so_no_rust_nao_roda_ferramentas_do_fx(self) -> None:
        self.r.write("src/main.rs", "fn main() { println!(); }\n")
        self.r.git("add", "src/main.rs")
        res = self.r.run_hook("pre-commit")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertCalled("trufflehog git")  # a varredura vale para o repositório inteiro
        self.assertNotCalled("pnpm")
        self.assertIn("fronteira-fx", res.stdout + res.stderr)

    def test_lint_staged_falhando_bloqueia(self) -> None:
        self.r.write("fronteira-fx/src/app.ts", "export const a = 2;\n")
        self.r.git("add", "fronteira-fx/src/app.ts")
        res = self.r.run_hook("pre-commit", env={"FAKE_PNPM_RC": "1"})
        self.assertNotEqual(res.returncode, 0)

    def test_binario_de_outra_versao_avisa_mas_varre(self) -> None:
        self.r.write("fronteira-fx/src/app.ts", "export const a = 2;\n")
        self.r.git("add", "fronteira-fx/src/app.ts")
        res = self.r.run_hook("pre-commit", env={"FAKE_TRUFFLEHOG_VERSION": "3.80.0"})
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("3.80.0", res.stdout + res.stderr, "o aviso deve dizer qual versão local foi encontrada")
        self.assertIn(HOOKS_VERSION, res.stdout + res.stderr, "o aviso deve dizer qual é a versão da CI")
        self.assertCalled("trufflehog git")

    def test_binario_na_versao_da_ci_nao_avisa(self) -> None:
        self.r.write("fronteira-fx/src/app.ts", "export const a = 2;\n")
        self.r.git("add", "fronteira-fx/src/app.ts")
        res = self.r.run_hook("pre-commit")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertNotIn("aviso", res.stdout + res.stderr)

    def test_py_em_stage_sem_uv_bloqueia_com_mensagem(self) -> None:
        os.remove(self.r.bin / "uv")
        self.r.write("fronteira-fx/backend/src/fx.py", "A = 2\n")
        self.r.git("add", "fronteira-fx/backend/src/fx.py")
        res = self.r.run_hook("pre-commit")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("uv", res.stdout + res.stderr)
        self.assertNotCalled("pnpm")

    def test_ts_em_stage_sem_uv_nao_precisa_de_uv(self) -> None:
        os.remove(self.r.bin / "uv")
        self.r.write("fronteira-fx/src/app.ts", "export const a = 2;\n")
        self.r.git("add", "fronteira-fx/src/app.ts")
        res = self.r.run_hook("pre-commit")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertCalled("pnpm exec lint-staged")

    def test_docker_e_usado_com_versao_fixa_quando_nao_ha_binario(self) -> None:
        os.remove(self.r.bin / "trufflehog")
        self.r.write("fronteira-fx/src/app.ts", "export const a = 2;\n")
        self.r.git("add", "fronteira-fx/src/app.ts")
        res = self.r.run_hook("pre-commit", env={"FAKE_DOCKER_INFO_RC": "0", "FAKE_TRUFFLEHOG_RC": "183"})
        self.assertNotEqual(res.returncode, 0)
        run = self.assertCalled("docker run")
        self.assertIn(f"trufflesecurity/trufflehog:{HOOKS_VERSION}", run)
        self.assertNotIn(":latest", run)
        self.assertIn("--only-verified", run)
        self.assertIn("TRUFFLEHOG-DOCKER-SAIDA-VISIVEL", res.stderr)
        self.assertIn("Commit bloqueado", res.stdout + res.stderr)

    def test_docker_num_worktree_monta_o_repositorio_principal(self) -> None:
        # Num worktree, .git é um arquivo que aponta para fora de $PWD; o container precisa ver esse diretório.
        os.remove(self.r.bin / "trufflehog")
        worktree = self.r.root / "arvore"
        self.r.git("worktree", "add", "-q", "-b", "wt", str(worktree))
        (worktree / "fronteira-fx" / "src" / "app.ts").write_text("export const a = 9;\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "fronteira-fx/src/app.ts"],
            cwd=worktree, env={**os.environ, "PATH": self.r.path, "GIT_CONFIG_NOSYSTEM": "1", "HOME": str(self.r.root)},
            check=True,
        )
        res = self.r.run_hook("pre-commit", env={"FAKE_DOCKER_INFO_RC": "0"}, cwd=worktree)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        run = self.assertCalled("docker run")
        common = self.r.git("rev-parse", "--path-format=absolute", "--git-common-dir")
        self.assertIn(f"-v {worktree}:/repo", run)
        self.assertIn(f"-v {common}:{common}:ro", run, "o diretório .git principal deve ser montado no mesmo caminho")

    def test_docker_no_checkout_principal_nao_monta_nada_a_mais(self) -> None:
        os.remove(self.r.bin / "trufflehog")
        self.r.write("fronteira-fx/src/app.ts", "export const a = 2;\n")
        self.r.git("add", "fronteira-fx/src/app.ts")
        res = self.r.run_hook("pre-commit", env={"FAKE_DOCKER_INFO_RC": "0"})
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        run = self.assertCalled("docker run")
        self.assertEqual(run.count(" -v "), 1, run)


class PreCommitSemTruffleHog(HookTestCase):
    with_trufflehog = False

    def test_sem_binario_e_sem_docker_avisa_e_segue(self) -> None:
        self.r.write("fronteira-fx/src/app.ts", "export const a = 2;\n")
        self.r.git("add", "fronteira-fx/src/app.ts")
        res = self.r.run_hook("pre-commit", env={"FAKE_DOCKER_INFO_RC": "1"})
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("trufflehog indisponível", res.stdout + res.stderr)
        self.assertNotCalled("docker run")
        self.assertCalled("pnpm exec lint-staged")

    def test_fx_require_secret_scan_transforma_aviso_em_falha(self) -> None:
        self.r.write("fronteira-fx/src/app.ts", "export const a = 2;\n")
        self.r.git("add", "fronteira-fx/src/app.ts")
        res = self.r.run_hook("pre-commit", env={"FAKE_DOCKER_INFO_RC": "1", "FX_REQUIRE_SECRET_SCAN": "1"})
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("FX_REQUIRE_SECRET_SCAN", res.stdout + res.stderr)
        self.assertNotCalled("pnpm")


class PrePush(HookTestCase):
    def _line(self, local_sha: str, remote_sha: str, ref: str = "refs/heads/main") -> str:
        return f"{ref} {local_sha} {ref} {remote_sha}\n"

    def test_varre_so_os_commits_novos_e_roda_testes_quando_fx_muda(self) -> None:
        head = self.r.commit("fronteira-fx/src/app.ts", "export const a = 3;\n", "fx")
        res = self.r.run_hook("pre-push", stdin=self._line(head, self.r.base_sha))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        scan = self.assertCalled("trufflehog git")
        self.assertIn(f"--since-commit {self.r.base_sha}", scan)
        self.assertIn("--only-verified", scan)
        self.assertIn("--fail", scan)
        self.assertCalled("pnpm exec vitest run")

    def test_mudanca_no_backend_roda_pytest(self) -> None:
        head = self.r.commit("fronteira-fx/backend/src/fx.py", "A = 2\n", "backend")
        res = self.r.run_hook("pre-push", stdin=self._line(head, self.r.base_sha))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertCalled("uv run pytest")

    def test_push_so_do_rust_nao_roda_testes_do_fx(self) -> None:
        head = self.r.commit("src/main.rs", "fn main() { let _x = 1; }\n", "rust")
        res = self.r.run_hook("pre-push", stdin=self._line(head, self.r.base_sha))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertCalled("trufflehog git")
        self.assertNotCalled("pnpm")
        self.assertNotCalled("uv")

    def test_ref_nova_varre_historico_inteiro_e_roda_tudo(self) -> None:
        head = self.r.commit("src/main.rs", "fn main() { let _x = 1; }\n", "rust")
        res = self.r.run_hook("pre-push", stdin=self._line(head, ZERO_SHA, ref="refs/heads/nova"))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        scan = self.assertCalled("trufflehog git")
        self.assertNotIn("--since-commit", scan)
        self.assertCalled("pnpm exec vitest run")
        self.assertCalled("uv run pytest")

    def test_scanner_que_le_stdin_nao_engole_as_outras_refs(self) -> None:
        # O Git entrega as refs pelo stdin do hook; uma ferramenta chamada dentro do laço não pode consumi-lo.
        a = self.r.commit("src/main.rs", "fn main() { let _a = 1; }\n", "rust a")
        b = self.r.commit("src/main.rs", "fn main() { let _b = 2; }\n", "rust b")
        stdin = self._line(b, self.r.base_sha, ref="refs/heads/main") + self._line(a, ZERO_SHA, ref="refs/heads/outra")
        res = self.r.run_hook("pre-push", stdin=stdin, env={"FAKE_TRUFFLEHOG_EAT_STDIN": "1"})
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        scans = [line for line in self.r.calls() if line.startswith("trufflehog git")]
        self.assertEqual(len(scans), 2, f"cada ref enviada deve ser varrida; chamadas: {self.r.calls()}")

    def test_remocao_de_ref_remota_nao_varre_nem_testa(self) -> None:
        res = self.r.run_hook("pre-push", stdin=self._line(ZERO_SHA, self.r.base_sha, ref="refs/heads/velha"))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertNotCalled("trufflehog")
        self.assertNotCalled("pnpm")

    def test_segredo_verificado_bloqueia_o_push_com_mensagem(self) -> None:
        head = self.r.commit("fronteira-fx/src/app.ts", "export const a = 3;\n", "fx")
        res = self.r.run_hook("pre-push", stdin=self._line(head, self.r.base_sha), env={"FAKE_TRUFFLEHOG_RC": "183"})
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Push bloqueado", res.stdout + res.stderr)
        self.assertIn("TRUFFLEHOG-SAIDA-VISIVEL", res.stderr)
        self.assertNotCalled("pnpm")

    def test_pytest_falhando_bloqueia(self) -> None:
        head = self.r.commit("fronteira-fx/backend/src/fx.py", "A = 2\n", "backend")
        res = self.r.run_hook("pre-push", stdin=self._line(head, self.r.base_sha), env={"FAKE_UV_RC": "1"})
        self.assertNotEqual(res.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
    sys.exit(0)
