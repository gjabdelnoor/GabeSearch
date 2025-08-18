# 🔍 GabeSearch MCP - multiple searches in one tool call!

NOTE: I made this with the help of Sonnet 4, moderate your expectations accordingly.

The reason I made this as such a botch job was I noticed that the Fetch and Playwright tools would only pull one website or perform one action per tool call. If you are using local inference with limited context windows and dodgy tool use, this can quickly become unusable for QA applications. The solution was to have multiple searxng queries running in parallel, to have one big tool call instead of multiple small tool calls that rot the context window.

That being said, I come from a non-technical background, and at the risk of overstating issues with this extension, when I made it Sonnet 4 and God knew how it works. So When you try to use this I recommend querying both to see where that gets you.

[![Docker](https://img.shields.io/badge/Docker-Required-blue?logo=docker)](https://docker.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![LM Studio](https://img.shields.io/badge/LM%20Studio-MCP%20Extension-green)](https://lmstudio.ai)

A fully local Retrieval Augmented Generation (RAG) system that gives [LM Studio](https://lmstudio.ai) access to real-time web search without any API keys or paid services.


## ✨ Features

- 🌐 **Real-time web search** - Access current information from search engines, improve QA performance.
- 🏠 **100% local** - No API keys, no external services, 100% free
- ⚡ **Parallel processing** - Fetches multiple sources simultaneously in one tool call minimizing context bloat and prompt processing.
- 🐳 **One-click setup** - Containerized with Docker for easy deployment
- 🔧 **Cross-platform** - Works on Windows, Mac, and Linux
- 🔄 **Engine rotation** - Rotates queries across multiple engines with randomized browser headers and automatic fallbacks to avoid CAPTCHAs.


## 🚀 Quick Start

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- [LM Studio](https://lmstudio.ai) installed

### Installation

1. **Clone this repository**:
   ```bash
   git clone https://github.com/yourusername/local-rag-lm-studio.git
   cd local-rag-lm-studio
   ```

2. **Start the services**:
   
   **Windows:**
   ```cmd
   start_servers.bat
   ```
   
   **Mac/Linux:**
   ```bash
   chmod +x start_servers.sh
   ./start_servers.sh
   ```

3. **Configure LM Studio**:
   - Open LM Studio
   - Go to Settings → Developer → MCP Settings
   - Copy the contents of `lm-studio-config/mcp.json` into your MCP configuration
   - Restart LM Studio

4. **Start searching!** 🎉

## 💻 Usage

The tool accepts search queries in JSON format:

```json
{
  "queries": [
    "latest developments in AI safety research 2024",
    "OpenAI GPT-4 performance benchmarks",
    "machine learning ethics guidelines"
  ],
  "claim": "Recent advances in AI safety and ethics"
}
```

Or use structured text format:

```
QUERIES:
1. latest developments in AI safety research 2024
2. OpenAI GPT-4 performance benchmarks
3. machine learning ethics guidelines

CLAIM:
Recent advances in AI safety and ethics
```

### Networking

SearXNG now runs behind a lightweight nginx proxy on port 8888. The proxy injects `X-Forwarded-For` and `X-Real-IP` headers and loads rate-limit rules from `limiter.toml`, helping search engines apply their limits without returning CAPTCHA pages.

### Reliability

Queries randomize typical browser headers and rotate between multiple search engines. If one engine returns no results (for example, due to a CAPTCHA), the tool automatically retries with the next engine.

### Docker build

To create a portable image of the MCP server you can run:

```bash
docker build . -t gabesearch:latest
```

This image contains only the bulk search server. Use the provided `docker compose` setup or your own SearXNG instance to handle search requests.

