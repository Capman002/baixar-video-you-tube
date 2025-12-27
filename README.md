<div align="center">

# Baixar Vídeo

### Ferramenta profissional para download de vídeos

<br/>

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![yt-dlp](https://img.shields.io/badge/yt--dlp-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](https://github.com/yt-dlp/yt-dlp)
[![License](https://img.shields.io/badge/License-MIT-F7DF1E?style=for-the-badge)](LICENSE)

<br/>

**Plataformas Suportadas**

[![YouTube](https://img.shields.io/badge/YouTube-FF0000?style=flat-square&logo=youtube&logoColor=white)](https://youtube.com)
[![Instagram](https://img.shields.io/badge/Instagram-E4405F?style=flat-square&logo=instagram&logoColor=white)](https://instagram.com)
[![TikTok](https://img.shields.io/badge/TikTok-000000?style=flat-square&logo=tiktok&logoColor=white)](https://tiktok.com)
[![X](https://img.shields.io/badge/X-000000?style=flat-square&logo=x&logoColor=white)](https://x.com)
[![Facebook](https://img.shields.io/badge/Facebook-1877F2?style=flat-square&logo=facebook&logoColor=white)](https://facebook.com)
[![Vimeo](https://img.shields.io/badge/Vimeo-1AB7EA?style=flat-square&logo=vimeo&logoColor=white)](https://vimeo.com)
[![Twitch](https://img.shields.io/badge/Twitch-9146FF?style=flat-square&logo=twitch&logoColor=white)](https://twitch.tv)
[![Reddit](https://img.shields.io/badge/Reddit-FF4500?style=flat-square&logo=reddit&logoColor=white)](https://reddit.com)

</div>

---

<div align="center">

![Interface](docs/images/image.png)

</div>

## Visão Geral

Aplicação web de código aberto para download de vídeos de diversas plataformas. Interface moderna com suporte a múltiplos formatos, qualidades e playlists.

### Funcionalidades Principais

| Recurso                  | Descrição                                            |
| ------------------------ | ---------------------------------------------------- |
| **Multi-formato**        | Download em MP4 (vídeo) ou MP3 (áudio)               |
| **Seleção de qualidade** | 360p, 480p, 720p, 1080p, 1440p, 4K                   |
| **Suporte a playlists**  | Download de playlists com seleção individual         |
| **Preview**              | Visualização de informações antes do download        |
| **Fila de downloads**    | Processamento sequencial com progresso em tempo real |
| **Histórico**            | Registro persistente de downloads realizados         |
| **Multi-plataforma**     | Suporte a 1000+ sites via yt-dlp                     |

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENTE                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    Interface Web                           │  │
│  │              HTML + Tailwind + Socket.IO                   │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ WebSocket / HTTP
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         SERVIDOR                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   FastAPI   │  │  Socket.IO  │  │      SQLite (async)     │  │
│  │   (REST)    │  │  (Realtime) │  │       Histórico         │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
│                              │                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    Download Engine                         │  │
│  │         yt-dlp + FFmpeg + POT Provider (anti-bot)          │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Stack Tecnológica

| Camada          | Tecnologia                      |
| --------------- | ------------------------------- |
| Runtime         | Python 3.11+                    |
| Framework       | FastAPI + Uvicorn               |
| Realtime        | python-socketio                 |
| Database        | SQLite + aiosqlite + SQLAlchemy |
| Download        | yt-dlp + FFmpeg                 |
| Auth            | bgutil-ytdlp-pot-provider       |
| Package Manager | UV                              |

---

## Instalação

### Requisitos

- Python 3.11 ou superior
- FFmpeg instalado e no PATH
- Docker (opcional, para POT Provider)

### Desenvolvimento Local

```bash
# Clonar repositório
git clone <url-do-repositorio>
cd baixar-video

# (Opcional) Iniciar POT Provider para bypass de proteções
docker run -d -p 4416:4416 --name pot-provider brainicism/bgutil-ytdlp-pot-provider

# Instalar dependências
pip install uv
uv sync

# Iniciar servidor
uv run uvicorn src.main:socket_app --reload --host 0.0.0.0 --port 8000
```

### Produção (Docker Compose)

```bash
docker compose up -d
```

---

## Estrutura do Projeto

```
baixar-video/
├── src/
│   ├── main.py             # Aplicação FastAPI + rotas + eventos Socket.IO
│   ├── downloader.py       # Serviço de download (yt-dlp wrapper)
│   ├── preview.py          # Serviço de preview (extract_info)
│   ├── queue_manager.py    # Gerenciador de fila de downloads
│   ├── database.py         # Conexão SQLite + CRUD
│   ├── models.py           # Schemas Pydantic + modelos SQLAlchemy
│   ├── settings.py         # Configurações centralizadas
│   └── templates/
│       └── index.html      # Interface web (SPA)
├── data/                   # Banco de dados SQLite
├── downloads/              # Arquivos baixados (temporário)
├── pyproject.toml          # Dependências (PEP 621)
├── Dockerfile              # Build de produção
├── docker-compose.yml      # Orquestração
└── README.md
```

---

## API Reference

### Endpoints REST

| Método   | Endpoint                 | Descrição                           |
| -------- | ------------------------ | ----------------------------------- |
| `GET`    | `/`                      | Interface web                       |
| `GET`    | `/api/preview?url=`      | Obtém informações do vídeo/playlist |
| `POST`   | `/api/download`          | Inicia novo download                |
| `GET`    | `/api/download/{job_id}` | Status de um download               |
| `DELETE` | `/api/download/{job_id}` | Cancela download                    |
| `GET`    | `/api/queue`             | Estado da fila                      |
| `GET`    | `/api/history`           | Histórico de downloads              |
| `DELETE` | `/api/history/{job_id}`  | Remove do histórico                 |
| `DELETE` | `/api/history`           | Limpa histórico                     |
| `GET`    | `/api/files/{filename}`  | Download de arquivo                 |
| `GET`    | `/api/info`              | Informações da aplicação            |

### Eventos Socket.IO

| Evento              | Direção         | Descrição                  |
| ------------------- | --------------- | -------------------------- |
| `start_download`    | Client → Server | Inicia download            |
| `download_queued`   | Server → Client | Download adicionado à fila |
| `download_progress` | Server → Client | Progresso do download      |
| `download_complete` | Server → Client | Download concluído         |
| `download_error`    | Server → Client | Erro no download           |
| `queue_update`      | Server → Client | Atualização da fila        |

---

## Configuração

| Variável           | Descrição           | Padrão                  |
| ------------------ | ------------------- | ----------------------- |
| `PORT`             | Porta do servidor   | `8000`                  |
| `POT_PROVIDER_URL` | URL do POT Provider | `http://localhost:4416` |

---

## Troubleshooting

| Problema               | Causa Provável         | Solução                                    |
| ---------------------- | ---------------------- | ------------------------------------------ |
| Erro 403 Forbidden     | POT Provider inativo   | Verificar `docker ps` ou iniciar container |
| Áudio não reproduz     | Codec incompatível     | FFmpeg converte para AAC automaticamente   |
| Download não inicia    | URL inválida           | Verificar se a plataforma é suportada      |
| Progresso não atualiza | WebSocket desconectado | Verificar conexão no footer da interface   |

---

## Licença

Distribuído sob a licença MIT. Veja [LICENSE](LICENSE) para mais informações.

---

## Aviso Legal

Esta ferramenta destina-se exclusivamente a fins educacionais e pessoais. O usuário é integralmente responsável por garantir que a utilização esteja em conformidade com os termos de serviço das plataformas e a legislação de direitos autorais vigente.

---

<div align="center">

**Desenvolvido com FastAPI e yt-dlp**

[![Python](https://img.shields.io/badge/Made_with-Python-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/Powered_by-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)

</div>
