import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-md space-y-4 py-12 text-center">
      <p className="tnum text-5xl font-semibold tracking-tight text-muted">404</p>
      <h2 className="text-lg font-semibold tracking-tight">Esta página não existe</h2>
      <p className="text-sm text-muted">O endereço pode ter mudado. As telas do terminal estão no menu ao lado (ou em «Mais», no celular).</p>
      <Button asChild>
        <Link href="/">Ir para o início</Link>
      </Button>
    </div>
  );
}
