<div align="center">

# Site Health Check
*Monitoramento blackbox de rede e infraestrutura*

[![Status](https://img.shields.io/badge/status-MVP-blue.svg)](#)

[Funcionalidades](#funcionalidades) • [Targets Suportados](#targets-suportados) • [Instalação](#instalação) • [Arquitetura](#arquitetura)

</div>

O Site Health Check testa a disponibilidade e o tempo de resposta da sua infraestrutura de fora para dentro, sem precisar de agentes instalados nos servidores. Consiste em uma interface de filtragem e display combinada a uma engine de coleta.

> [!NOTE]
> O projeto está na fase de MVP. A engine de execução é estável, enquanto o frontend continua recebendo iterações focadas em usabilidade.

## Funcionalidades

- **Schedules Automáticos** - Configure a frequência (ex: a cada 5 minutos) e a engine dispara testes sequenciais contra os targets mapeados.
- **Recursive SAN Check** - Ao analisar certificados TLS/SSL, a engine extrai automaticamente os Subject Alternative Names (SANs) e pode mapeá-los/escaneá-los de forma recursiva.
- **Histórico Consolidado** - Base de dados para analisar estabilidade, identificar lentidões recorrentes e falhas em horários de pico.
- **Filtragem Avançada** - A interface permite investigar a rede isolando serviços específicos, mesmo dentro de blocos de IP muito amplos.

## O que a engine coleta

Em cada requisição de rede, os seguintes dados são processados:
- Tempo total de resposta (latências TCP e HTTP)
- Status de disponibilidade e redirecionamentos
- Resoluções de DNS e Headers do servidor
- Dados de certificados TLS/SSL (validação, expiração, issuer e versão do protocolo TLS)

## Targets Suportados

A flexibilidade de configuração permite definir *targets* com alta granularidade. Exemplos:

- **Domínios e URLs:** `https://api.exemplo.com.br/health`
- **Ranges de IPs (CIDR):** `192.168.1.0/24` ou `10.0.0.0/8` para varreduras em blocos inteiros.
- **Portas Específicas:** Testes focados em serviços não padronizados, ex: `10.0.0.50:8080`.

## Capturas de Tela

**Dashboard**  
Visão geral com o status consolidado da infraestrutura para validação rápida de interrupções ativas.  
<img src="./assets/screenshot-1.png" alt="Dashboard" width="800" style="margin-bottom: 20px;">

**Live Scan**  
Permite disparar varreduras imediatas para investigar o comportamento dos targets em tempo real.  
<img src="./assets/screenshot-2.png" alt="Live Scan" width="800" style="margin-bottom: 20px;">

**Scheduled Scans**  
Adicione e gerencie rotinas automáticas de execução, ajustando a frequência e os parâmetros para o monitoramento contínuo.  
<img src="./assets/screenshot-3.png" alt="Scheduled Scans" width="800">

## Avisos de Uso

> [!WARNING]
> Isso é uma ferramenta de monitoramento externo. Não substitui o profiling interno da aplicação (ex: descobrir em qual tabela do banco de dados uma query engasgou).

> [!CAUTION]
> Cuidado com rate limits. Configurar schedules agressivos em infraestruturas que você não controla pode resultar no bloqueio do seu IP ou gerar negação de serviço acidental. O objetivo é monitorar, não sobrecarregar.

## Instalação

**Pré-requisitos:**
- Container runtime (Docker ou Podman)
- Ambientes Python e Node.js (Apenas para desenvolvimento local fora de containers)

1. Clone o repositório e abra o terminal na raiz.
2. Inicie os containers:
   ```bash
   docker compose up --build -d
   ```
3. Acesse:
   - **Frontend:** `http://localhost:8080`
   - **Backend API:** `http://localhost:8000`

## CI/CD

O deploy é automatizado via GitLab CI/CD com um pipeline de estágio único (`deploy`).

### Pipeline

| Job | Branch trigger | Environment | O que faz |
|---|---|---|---|
| `deploy_local_staging` | `local-staging` | `local-staging` | Deploy no servidor de staging local |
| `deploy_production` | `production` | `production` | Deploy no servidor de produção |

Cada job executa:
1. Gera o `.env` a partir das variáveis CI/CD
2. Executa `init-letsencrypt.sh` (gera certificados SSL)
3. `docker compose up -d --build` (build e deploy dos containers)
4. `docker system prune` (limpeza de imagens antigas)

### Runner

O pipeline espera um runner com a tag `tcp-scanner` usando o executor `shell`. O runner precisa de:
- Podman (com `docker` como alias ou symlink)
- `podman-compose` instalado
- SubUID/SubGID configurados para o usuário do runner (rootless)
- `loginctl enable-linger` habilitado para o usuário do runner

### Variáveis CI/CD (GitLab → Settings → CI/CD → Variables)

| Variável | Scope | Obrigatória | Descrição |
|---|---|---|---|
| `DOMAIN_NAME` | Per-environment | Sim | Domínio do servidor (ex: `exemplo.com.br`) |
| `CERTBOT_EMAIL` | Per-environment | Sim | E-mail para registro no Let's Encrypt |
| `ENABLE_SSL` | Per-environment | Sim | `true` para habilitar HTTPS |
| `LOCAL_HTTPS` | `local-staging` | Não | `true` para usar certificado local (bypassa Let's Encrypt) |
| `USE_STAGING_SSL` | Per-environment | Não | `true` para usar o ambiente staging do Let's Encrypt |
| `ALLOWED_IPS` | Per-environment | Não | Diretivas nginx de IP whitelist (ex: `allow 10.0.0.1;`) |
| `LOCAL_CA_DIR` | `local-staging` | Não | Caminho absoluto para o diretório da CA local no runner (ex: `/home/gitlab-runner/.local-ca`) |

> [!TIP]
> Para staging local, defina as variáveis com scope no environment `local-staging`. Para produção, use o scope `production`. Variáveis sem scope se aplicam a todos os environments.

## Arquitetura

O projeto é dividido em três frentes principais:
1. **Frontend:** Interface SPA interativa no navegador.
2. **Backend (API):** Gerencia os schedules, recebe configurações e serve os dados coletados (construído em FastAPI).
3. **Engine:** O executor independente que realiza as chamadas de rede e coleta os dados brutos.

Para desenvolvimento local do backend (utilizando o [uv](https://docs.astral.sh/uv/), que também instala o Python fixado em `.python-version`):
```bash
uv sync          # cria .venv com api + engine
uv run pytest    # roda os testes
```

A documentação interativa da API (Swagger/ReDoc) pode ser acessada em `http://localhost:8000/docs` com o backend em execução.