/** Erro HTTP da API (ou da demonstração, que responde com o mesmo formato). Fica fora do client para evitar ciclos. */
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
