# Baixar Vídeo

Ferramenta de código aberto para download de vídeos do YouTube em alta qualidade.

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green?logo=fastapi&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow)

## 📋 Sobre

Este projeto permite baixar vídeos do YouTube de forma simples e rápida, com interface web moderna e suporte a download em tempo real via WebSocket.

### Funcionalidades

- ✅ Download de vídeos em alta qualidade (até 4K)
- ✅ Conversão automática para MP4 com áudio AAC
- ✅ Barra de progresso em tempo real
- ✅ Interface responsiva e minimalista
- ✅ Bypass automático de proteções anti-bot
- ✅ Pronto para deploy em Docker

## 🏗️ Arquitetura

```text
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Interface     │───▶│   Backend        │───▶│  POT Provider   │
│   (Browser)     │    │  (FastAPI)       │    │  (Docker)       │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌──────────────────┐
                       │   yt-dlp + FFmpeg │
                       └──────────────────┘
```

**Stack Tecnológica:**

- **Backend:** FastAPI + Uvicorn (Python 3.11+)
- **Gerenciador:** UV (gerenciador de pacotes moderno)
- **Engine:** yt-dlp + FFmpeg
- **Anti-Bot:** bgutil-ytdlp-pot-provider
- **Real-time:** Socket.IO

## 🚀 Instalação

### Pré-requisitos

- Python 3.11 ou superior
- Docker (para o POT Provider)
- FFmpeg (incluído no Docker, ou instale localmente)

### Desenvolvimento Local

```bash
# Clone o repositório
git clone <url-do-repositorio>
cd baixar-video

# Inicie o servidor POT Provider
docker run -d -p 4416:4416 --name pot-provider brainicism/bgutil-ytdlp-pot-provider

# Instale as dependências
pip install uv
uv sync

# Inicie o servidor
uv run uvicorn src.main:socket_app --reload

# Acesse: http://localhost:8000
```

### Produção (Docker Compose)

```bash
docker compose up -d
```

Isso inicia automaticamente o POT Provider e o Backend.

## 📁 Estrutura do Projeto

```text
baixar-video/
├── src/
│   ├── main.py           # Aplicação FastAPI
│   ├── downloader.py     # Serviço de download
│   ├── settings.py       # Configurações
│   └── templates/
│       └── index.html    # Interface web
├── downloads/            # Pasta temporária de downloads
├── pyproject.toml        # Dependências (UV/PEP 621)
├── Dockerfile            # Build de produção
├── docker-compose.yml    # Orquestração multi-serviço
└── README.md
```

## ⚙️ Configuração

| Variável de Ambiente | Descrição           | Padrão                  |
| -------------------- | ------------------- | ----------------------- |
| `PORT`               | Porta do servidor   | `8000`                  |
| `POT_PROVIDER_URL`   | URL do servidor POT | `http://localhost:4416` |

## 🔧 Solução de Problemas

| Problema           | Solução                                                |
| ------------------ | ------------------------------------------------------ |
| Erro 403 Forbidden | Verifique se o POT Provider está rodando (`docker ps`) |
| Áudio não funciona | O FFmpeg deve estar instalado e no PATH                |
| Download lento     | Verifique sua conexão de internet                      |

## 📜 Licença

Este projeto está licenciado sob a [Licença MIT](LICENSE).

## ⚠️ Aviso Legal

Esta ferramenta é fornecida apenas para fins educacionais. O usuário é responsável por garantir que o uso desta ferramenta esteja em conformidade com os Termos de Serviço do YouTube e as leis de direitos autorais aplicáveis.

---

Desenvolvido com ❤️ usando Python e FastAPI
