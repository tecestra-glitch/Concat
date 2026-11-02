# Varredura de segredos compartilhada pelos hooks pre-commit e pre-push.
# Carregar com `. ./fronteira-fx/.husky/scan-secrets.sh`, com o diretório atual na raiz do repositório.
#
# Ordem de preferência: o binário `trufflehog` no PATH; senão a imagem oficial, na mesma versão, via
# Docker (só com daemon disponível); senão avisa e segue, a menos que FX_REQUIRE_SECRET_SCAN=1.
# A saída do TruffleHog fica visível de propósito: quando ele bloqueia, dá para ver arquivo e detector.

# Mesma versão fixada na CI (.github/workflows/secret-scan.yml). A tag da imagem no Docker Hub não tem o "v".
TRUFFLEHOG_VERSION="3.99.7"

# scan_secrets [args do trufflehog...]
# Códigos de saída: 0 (nada verificado, ou varredura indisponível e não obrigatória); 183 (segredo
# verificado, pelo --fail); 127 (varredura obrigatória e indisponível); outro (erro da própria ferramenta).
# Chamar sempre como `scan_secrets ... || rc=$?`, para o `set -e` não encerrar o hook antes da mensagem.
scan_secrets() {
  if command -v trufflehog >/dev/null 2>&1; then
    # O binário local pode estar em outra versão; avisa, sem bloquear, para os detectores não divergirem da CI.
    _installed=$(trufflehog --version 2>&1 || true)
    case $_installed in
      *"$TRUFFLEHOG_VERSION"*) ;;
      *) echo "aviso: trufflehog local (${_installed:-versão desconhecida}) difere da versão da CI ($TRUFFLEHOG_VERSION)." >&2 ;;
    esac
    # Sem GIT_INDEX_FILE: no pre-commit o Git exporta o caminho do índice, que num worktree é absoluto; o
    # TruffleHog clona o repositório e o checkout desse clone herdaria a variável e reescreveria o índice
    # do commit em andamento (o commit sairia sem as mudanças em stage, ou um merge com a árvore antiga).
    (
      unset GIT_INDEX_FILE
      trufflehog git "file://$PWD" --only-verified --fail --no-update "$@"
    )
  elif docker info >/dev/null 2>&1; then
    # Num worktree, .git é um arquivo que aponta para o repositório principal, fora de $PWD: esse diretório é
    # montado também (só leitura), no mesmo caminho, senão o Git dentro do container não abre o repositório.
    # safe.directory=*: dentro do container o repositório pertence a outro usuário, e o Git recusaria lê-lo.
    _common=$(git rev-parse --path-format=absolute --git-common-dir)
    if [ "$_common" != "$PWD/.git" ]; then
      set -- -v "$_common:$_common:ro" "trufflesecurity/trufflehog:$TRUFFLEHOG_VERSION" \
        git file:///repo --only-verified --fail --no-update "$@"
    else
      set -- "trufflesecurity/trufflehog:$TRUFFLEHOG_VERSION" \
        git file:///repo --only-verified --fail --no-update "$@"
    fi
    docker run --rm -v "$PWD:/repo" \
      -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0='*' \
      "$@"
  elif [ "${FX_REQUIRE_SECRET_SCAN:-0}" = "1" ]; then
    echo "erro: FX_REQUIRE_SECRET_SCAN=1, mas o trufflehog está indisponível (sem binário e sem daemon Docker)." >&2
    return 127
  else
    echo "aviso: trufflehog indisponível (sem binário e sem daemon Docker); varredura de segredos pulada." >&2
    return 0
  fi
}

# check_secrets <Commit|Push> [args do trufflehog...]
# Devolve 0 quando o caminho está livre; devolve 1, explicando, quando a operação deve ser bloqueada.
check_secrets() {
  _what=$1
  shift
  _rc=0
  scan_secrets "$@" || _rc=$?
  case $_rc in
    0) return 0 ;;
    183)
      echo "trufflehog: segredo verificado encontrado. $_what bloqueado." >&2
      echo "Trate a credencial como vazada: revogue ou troque no provedor antes de removê-la do código." >&2
      return 1
      ;;
    127) return 1 ;;
    *)
      echo "aviso: trufflehog terminou com código $_rc (erro da ferramenta, não bloqueante)." >&2
      return 0
      ;;
  esac
}
