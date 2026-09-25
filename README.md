# Reconstrução Histórica com IA — Streamlit

Aplicação para:
- enviar uma fotografia histórica principal;
- enviar referências de pessoa, casa, paisagem, croqui e outras imagens;
- reconstruir/restaurar a cena com Nano Banana;
- baixar a imagem reconstruída;
- gerar um vídeo curto com Veo 3.1;
- baixar o MP4.

## Instalação local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

No Windows:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Configure:

```text
.streamlit/secrets.toml
```

com:

```toml
GOOGLE_API_KEY = "SUA_CHAVE"
```

Execute:

```bash
streamlit run app.py
```

## Streamlit Community Cloud

Suba `app.py`, `requirements.txt`, `.gitignore` e demais arquivos para GitHub.
Não publique `.streamlit/secrets.toml` com uma chave real.

No Streamlit Community Cloud:
App → Settings → Secrets

Cole:

```toml
GOOGLE_API_KEY = "SUA_CHAVE"
```

## Observação

O uso dos modelos Gemini/Veo depende da disponibilidade, limites e cobrança
da conta Google/Gemini API.
