#!/usr/bin/env python3
"""
gen-workflow.py — gera um Workflow script de orquestração paralela
a partir do plano de projeto em ./dev/plano.md

Uso: python3 gen-workflow.py [plano.md] [output.js]
"""
import re
import sys
from pathlib import Path

TEMPLATE = '''\
// AUTO-GERADO por gen-workflow.py — edite conforme necessário
// Use: Workflow tool com este script para orquestração paralela

export const meta = {{
  name: '{name}',
  description: '{description}',
  phases: [
    {{ title: 'Scaffold', detail: 'Estrutura base + configurações' }},
    {{ title: 'Build',    detail: 'Implementação por domínio com worktrees' }},
    {{ title: 'QA',       detail: 'Testes, lint e revisão de segurança' }},
    {{ title: 'Merge',    detail: 'Integração, conflitos e commit final' }},
  ],
}}

// ── Domínios independentes (cada um recebe seu próprio worktree) ─────
const DOMAINS = [
{domains}]

const FINDINGS_SCHEMA = {{
  type: 'object',
  properties: {{
    domain: {{ type: 'string' }},
    files_created: {{ type: 'array', items: {{ type: 'string' }} }},
    files_modified: {{ type: 'array', items: {{ type: 'string' }} }},
    tests_passing: {{ type: 'boolean' }},
    notes: {{ type: 'string' }},
  }},
  required: ['domain', 'files_created', 'files_modified', 'tests_passing'],
}}

// ── Fase 1: Scaffold (sem worktree — cria estrutura base) ────────────
phase('Scaffold')
const scaffold = await agent(
  'Crie a estrutura base do projeto: pastas, arquivos de config, ' +
  'package.json/pyproject.toml, .gitignore, .env.example, README.md. ' +
  'Siga as preferências do usuário: pnpm, TypeScript strict, ESLint, Husky+TruffleHog.',
  {{ label: 'scaffold:base', phase: 'Scaffold' }}
)
log('Scaffold concluído: ' + scaffold)

// ── Fase 2: Build paralelo por domínio (worktree por agente) ─────────
phase('Build')
const results = await parallel(DOMAINS.map(d => () =>
  agent(
    `Você é o agente responsável pelo domínio: ${{d.key}}.\\n\\n` +
    `Objetivo: ${{d.goal}}\\n\\n` +
    `Escopo de arquivos: ${{d.scope}}\\n\\n` +
    `Contratos/interfaces que deve respeitar: ${{d.contracts || 'nenhum específico'}}\\n\\n` +
    `Não modifique arquivos fora do seu escopo. ` +
    `Ao terminar, rode os testes do seu domínio e confirme que passam.`,
    {{
      label: \`build:${{d.key}}\`,
      phase: 'Build',
      isolation: 'worktree',
      schema: FINDINGS_SCHEMA,
    }}
  )
))

const built = results.filter(Boolean)
log(\`${{built.length}}/${{DOMAINS.length}} domínios concluídos\`)

// ── Fase 3: QA paralelo ───────────────────────────────────────────────
phase('QA')
const QA_CHECKS = [
  {{ key: 'security', prompt: 'Auditoria de segurança: OWASP top 10, secrets no código, dependências com CVE. Reporte severity + remediação.' }},
  {{ key: 'quality',  prompt: 'Revisão de qualidade: testes faltando, código duplicado, complexidade alta, cobertura < 80 %. Reporte com arquivo:linha.' }},
  {{ key: 'perf',     prompt: 'Auditoria de performance: N+1 queries, bundle size, re-renders desnecessários. Só problemas concretos com evidência.' }},
]
const qa = await parallel(QA_CHECKS.map(c => () =>
  agent(c.prompt, {{ label: \`qa:${{c.key}}\`, phase: 'QA' }})
))
log('QA concluído')

// ── Fase 4: Merge e commit ────────────────────────────────────────────
phase('Merge')
const merged = await agent(
  \`Integre os resultados de ${{built.length}} domínios.\\n\` +
  \`Findings de QA:\\n${{qa.filter(Boolean).join('\\n---\\n')}}\\n\\n\` +
  \`Resolva conflitos de merge, rode todos os testes, faça um commit final ` +
  \`com mensagem descritiva seguindo Conventional Commits.\`,
  {{ label: 'merge:final', phase: 'Merge' }}
)

return {{
  domains_built: built.length,
  qa_checks: qa.filter(Boolean).length,
  result: merged,
}}
'''


def parse_domains(plano: str) -> list[dict]:
    """Extrai domínios de um plano.md (linhas com ## ou ### e checkboxes)."""
    domains = []
    current = None
    for line in plano.splitlines():
        m = re.match(r'^#{2,3}\s+(.+)', line)
        if m:
            if current:
                domains.append(current)
            current = {'key': re.sub(r'[^a-z0-9]', '-', m.group(1).lower()).strip('-'),
                       'goal': m.group(1), 'scope': [], 'contracts': ''}
        elif current and re.match(r'^\s*-\s*\[', line):
            task = re.sub(r'^\s*-\s*\[[x ]\]\s*', '', line).strip()
            current['scope'].append(task)
    if current:
        domains.append(current)
    return domains or [
        {'key': 'backend',  'goal': 'Implementar backend e API', 'scope': ['src/backend/**'], 'contracts': ''},
        {'key': 'frontend', 'goal': 'Implementar frontend',      'scope': ['src/frontend/**'], 'contracts': ''},
        {'key': 'tests',    'goal': 'Escrever testes',           'scope': ['tests/**'],        'contracts': ''},
        {'key': 'docs',     'goal': 'Escrever documentação',     'scope': ['docs/**'],         'contracts': ''},
    ]


def main():
    plano_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('./dev/plano.md')
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('./dev/workflow-start.js')

    plano = plano_path.read_text(encoding='utf-8') if plano_path.exists() else ''
    domains = parse_domains(plano)

    # Extrair nome do projeto do plano
    name_match = re.search(r'^#\s+(.+)', plano, re.MULTILINE)
    project_name = name_match.group(1) if name_match else output_path.parent.parent.name

    domains_js = ',\n'.join(
        f'  {{ key: {d["key"]!r}, goal: {d["goal"]!r}, '
        f'scope: {", ".join(d["scope"][:3])!r}, contracts: {d["contracts"]!r} }}'
        for d in domains
    )

    script = TEMPLATE.format(
        name=re.sub(r'[^a-z0-9-]', '-', project_name.lower()),
        description=f'Orquestração paralela do projeto {project_name}',
        domains=domains_js + '\n',
    )

    output_path.write_text(script, encoding='utf-8')
    print(f'✅ Workflow gerado em {output_path}')
    print(f'   {len(domains)} domínios: {", ".join(d["key"] for d in domains)}')
    print(f'\nUso: Workflow tool com scriptPath: "{output_path}"')


if __name__ == '__main__':
    main()
