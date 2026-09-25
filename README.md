# Reconstrução Histórica com IA — versão corrigida

Aplicação Streamlit para reconstrução/restauração de fotografias históricas e geração de vídeos com Veo.

## Correção aplicada

Foi corrigido o bloco final de verificação da `GOOGLE_API_KEY` que estava com indentação inválida e causava:

`IndentationError: unindent does not match any outer indentation level`

O arquivo `app.py` foi validado com `python -m py_compile`.

## Configuração

1. Instale as dependências:

```bash
pip install -r requirements.txt
```

2. Crie `.streamlit/secrets.toml` a partir de `.streamlit/secrets.toml.example` e informe sua chave:

```toml
GOOGLE_API_KEY = "SUA_CHAVE"
```

3. Execute:

```bash
streamlit run app.py
```

Nunca publique sua chave de API no GitHub.
