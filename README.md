# ApiServelessAzure

Aplicacao serverless em Python para envio diario por e-mail dos compromissos da agenda.

## Estrutura

- `functions/function_app.py`: Azure Function com Timer Trigger diario as 14:00.
- `functions/data/agenda.json`: base de compromissos.
- `functions/local.settings.json.example`: exemplo de configuracao local.
- `functions/requirements.txt`: dependencias Python.

## Regra de execucao

A funcao `EnviarResumoAgenda` roda todos os dias as 14:00 com cron:

`0 0 14 * * *`

Ela consulta os compromissos de hoje e envia um e-mail com o resumo.

## API HTTP para agenda

Tambem foram criados endpoints HTTP para voce cadastrar e editar compromissos sem alterar o JSON manualmente.

### Endpoints

1. `GET /api/agenda` - lista compromissos
1. `POST /api/agenda` - cria compromisso
1. `PUT /api/agenda/{id}` - atualiza compromisso

Observacao: os endpoints estao com `auth_level=function`, entao voce deve enviar a `function key` ao chamar no Azure.

### Exemplo de criar compromisso

```powershell
$body = @{
  data = "2026-06-10"
  hora = "10:30"
  titulo = "Consulta medica"
  descricao = "Levar exames"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "http://localhost:7071/api/agenda" -ContentType "application/json" -Body $body
```

### Exemplo de atualizar compromisso

```powershell
$body = @{
  hora = "11:00"
  descricao = "Horario atualizado"
} | ConvertTo-Json

Invoke-RestMethod -Method Put -Uri "http://localhost:7071/api/agenda/1" -ContentType "application/json" -Body $body
```

### Exemplo de listar agenda

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:7071/api/agenda"
```

## Formato da agenda

Edite `functions/data/agenda.json` com um dos formatos abaixo:

1. Data especifica (YYYY-MM-DD)
1. Dia da semana (`segunda`, `terca`, `friday`, `monday` ou numero `0` a `6`, onde `0` e segunda)

Exemplo:

```json
{
  "compromissos": [
    {
      "data": "2026-06-08",
      "hora": "09:00",
      "titulo": "Daily do projeto",
      "descricao": "Alinhamento rapido com o time"
    },
    {
      "dia_semana": "segunda",
      "hora": "14:30",
      "titulo": "Revisar pendencias"
    }
  ]
}
```

## Configuracao local

1. Instale Python 3.10+ e Azure Functions Core Tools v4.
1. Entre em `ApiServelessAzure/functions`.
1. Crie `local.settings.json` a partir do arquivo de exemplo:

```powershell
Copy-Item .\local.settings.json.example .\local.settings.json
```

1. Ajuste os valores SMTP no `local.settings.json`:

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- `EMAIL_FROM`
- `EMAIL_TO` (um ou mais, separados por virgula)

1. Instale dependencias e execute localmente:

```powershell
pip install -r requirements.txt
func start
```

## Publicacao no Azure

1. Crie/publice a Function App com runtime Python.
1. Configure as Application Settings com as mesmas chaves do `local.settings.json`.
1. Para garantir disparo as 14:00 no Brasil (em vez de UTC), defina:

- `WEBSITE_TIME_ZONE = E. South America Standard Time`

1. Publique o codigo da pasta `functions`.

## Observacoes

- Se nao houver compromisso no dia, a funcao envia e-mail informando que a agenda esta vazia.
- Para Gmail, use App Password se a conta tiver MFA.
- Em producao, prefira persistir agenda em banco (ex.: Azure Table, Cosmos DB, SQL). O JSON local funciona bem para prototipo e ambiente de desenvolvimento.
