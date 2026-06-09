import datetime
import json
import logging
import os
import smtplib
from http import HTTPStatus
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import azure.functions as func

app = func.FunctionApp()

DAY_MAP_PT = {
    0: "segunda",
    1: "terca",
    2: "quarta",
    3: "quinta",
    4: "sexta",
    5: "sabado",
    6: "domingo",
}

DAY_MAP_EN = {
    0: "monday",
    1: "tuesday",
    2: "wednesday",
    3: "thursday",
    4: "friday",
    5: "saturday",
    6: "sunday",
}


def _agenda_path() -> Path:
    return Path(__file__).parent / "data" / "agenda.json"


def _normalize(value: str) -> str:
    normalized = value.strip().lower()
    replacements = {
        "á": "a",
        "à": "a",
        "â": "a",
        "ã": "a",
        "é": "e",
        "ê": "e",
        "í": "i",
        "ó": "o",
        "ô": "o",
        "õ": "o",
        "ú": "u",
        "ç": "c",
    }
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    return normalized


def _load_agenda() -> list[dict[str, Any]]:
    payload = _read_agenda_payload()

    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict) and isinstance(payload.get("compromissos"), list):
        return payload["compromissos"]

    logging.warning("Formato de agenda invalido. Esperado lista ou chave 'compromissos'.")
    return []


def _read_agenda_payload() -> Any:
    path = _agenda_path()
    if not path.exists():
        logging.warning("Arquivo de agenda nao encontrado em %s", path)
        return {"compromissos": []}

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _save_agenda(items: list[dict[str, Any]]) -> None:
    path = _agenda_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {"compromissos": items}
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def _next_id(items: list[dict[str, Any]]) -> int:
    ids = []
    for item in items:
        raw_id = item.get("id")
        if isinstance(raw_id, int):
            ids.append(raw_id)
            continue
        if isinstance(raw_id, str) and raw_id.isdigit():
            ids.append(int(raw_id))
    return max(ids, default=0) + 1


def _json_response(body: dict[str, Any], status_code: int = HTTPStatus.OK) -> func.HttpResponse:
    return func.HttpResponse(
        body=json.dumps(body, ensure_ascii=False),
        status_code=status_code,
        mimetype="application/json",
    )


def _parse_json_body(req: func.HttpRequest) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = req.get_json()
    except ValueError:
        return None, "Body invalido. Envie JSON valido."

    if not isinstance(data, dict):
        return None, "Body deve ser um objeto JSON."

    return data, None


def _validate_item(data: dict[str, Any], partial: bool = False) -> list[str]:
    errors: list[str] = []

    if not partial:
        if not data.get("hora"):
            errors.append("Campo 'hora' e obrigatorio.")
        if not data.get("titulo"):
            errors.append("Campo 'titulo' e obrigatorio.")
        if not data.get("data") and not data.get("dia_semana"):
            errors.append("Informe 'data' (YYYY-MM-DD) ou 'dia_semana'.")

    if data.get("data"):
        try:
            datetime.date.fromisoformat(str(data["data"]))
        except ValueError:
            errors.append("Campo 'data' deve estar no formato YYYY-MM-DD.")

    return errors


@app.function_name(name="ListarAgenda")
@app.route(route="agenda", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def listar_agenda(req: func.HttpRequest) -> func.HttpResponse:
    _ = req
    items = _load_agenda()
    return _json_response({"compromissos": items})


@app.function_name(name="CriarCompromisso")
@app.route(route="agenda", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def criar_compromisso(req: func.HttpRequest) -> func.HttpResponse:
    data, error = _parse_json_body(req)
    if error:
        return _json_response({"erro": error}, status_code=HTTPStatus.BAD_REQUEST)

    assert data is not None
    errors = _validate_item(data)
    if errors:
        return _json_response({"erros": errors}, status_code=HTTPStatus.BAD_REQUEST)

    items = _load_agenda()
    new_item = {
        "id": _next_id(items),
        "data": str(data.get("data", "")).strip(),
        "dia_semana": str(data.get("dia_semana", "")).strip(),
        "hora": str(data.get("hora", "")).strip(),
        "titulo": str(data.get("titulo", "")).strip(),
        "descricao": str(data.get("descricao", "")).strip(),
    }

    # Remove campos vazios para manter o JSON limpo.
    new_item = {key: value for key, value in new_item.items() if value != "" or key == "id"}

    items.append(new_item)
    _save_agenda(items)

    return _json_response(
        {"mensagem": "Compromisso criado com sucesso.", "compromisso": new_item},
        status_code=HTTPStatus.CREATED,
    )


@app.function_name(name="AtualizarCompromisso")
@app.route(route="agenda/{item_id:int}", methods=["PUT"], auth_level=func.AuthLevel.FUNCTION)
def atualizar_compromisso(req: func.HttpRequest) -> func.HttpResponse:
    item_id_raw = req.route_params.get("item_id", "")
    if not str(item_id_raw).isdigit():
        return _json_response({"erro": "ID invalido."}, status_code=HTTPStatus.BAD_REQUEST)

    item_id = int(item_id_raw)
    data, error = _parse_json_body(req)
    if error:
        return _json_response({"erro": error}, status_code=HTTPStatus.BAD_REQUEST)

    assert data is not None
    errors = _validate_item(data, partial=True)
    if errors:
        return _json_response({"erros": errors}, status_code=HTTPStatus.BAD_REQUEST)

    items = _load_agenda()
    index = next((i for i, item in enumerate(items) if int(item.get("id", -1)) == item_id), -1)
    if index == -1:
        return _json_response({"erro": "Compromisso nao encontrado."}, status_code=HTTPStatus.NOT_FOUND)

    allowed_fields = ["data", "dia_semana", "hora", "titulo", "descricao"]
    current_item = dict(items[index])

    for field in allowed_fields:
        if field in data:
            value = data[field]
            current_item[field] = str(value).strip() if value is not None else ""

    current_item = {key: value for key, value in current_item.items() if value != "" or key == "id"}

    if not current_item.get("data") and not current_item.get("dia_semana"):
        return _json_response(
            {"erro": "Compromisso precisa de 'data' ou 'dia_semana'."},
            status_code=HTTPStatus.BAD_REQUEST,
        )

    items[index] = current_item
    _save_agenda(items)

    return _json_response({"mensagem": "Compromisso atualizado com sucesso.", "compromisso": current_item})


def _is_for_today(item: dict[str, Any], today: datetime.date) -> bool:
    date_value = str(item.get("data", "")).strip()
    if date_value:
        return date_value == today.isoformat()

    weekday_value = str(item.get("dia_semana", "")).strip()
    if not weekday_value:
        return False

    normalized = _normalize(weekday_value)
    return normalized in {
        str(today.weekday()),
        DAY_MAP_PT[today.weekday()],
        DAY_MAP_EN[today.weekday()],
    }


def _format_items(items: list[dict[str, Any]], today: datetime.date) -> str:
    if not items:
        return (
            f"Ola!\n\n"
            f"Nao ha compromissos para {today.strftime('%d/%m/%Y')}.\n\n"
            "Mensagem automatica da sua agenda."
        )

    lines = [
        "Ola!",
        "",
        f"Seus compromissos para {today.strftime('%d/%m/%Y')}:",
        "",
    ]

    for item in items:
        hora = str(item.get("hora", "Sem horario")).strip() or "Sem horario"
        titulo = str(item.get("titulo", "Compromisso")).strip() or "Compromisso"
        descricao = str(item.get("descricao", "")).strip()

        lines.append(f"- {hora} | {titulo}")
        if descricao:
            lines.append(f"  {descricao}")

    lines.extend(["", "Mensagem automatica da sua agenda."])
    return "\n".join(lines)


def _send_email(subject: str, body: str) -> None:
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    email_from = os.getenv("EMAIL_FROM", smtp_user)
    email_to = os.getenv("EMAIL_TO", "ive1000@hotmail.com")

    required = [smtp_host, smtp_user, smtp_password, email_from, email_to]
    if not all(required):
        missing = [
            name
            for name, value in {
                "SMTP_HOST": smtp_host,
                "SMTP_USER": smtp_user,
                "SMTP_PASSWORD": smtp_password,
                "EMAIL_FROM": email_from,
                "EMAIL_TO": email_to,
            }.items()
            if not value
        ]
        raise ValueError(f"Variaveis ausentes para envio de email: {', '.join(missing)}")

    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = subject
    message["From"] = email_from
    message["To"] = email_to

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(email_from, [address.strip() for address in email_to.split(",")], message.as_string())


@app.function_name(name="EnviarResumoAgenda")
@app.schedule(schedule="0 0 14 * * *", arg_name="timer", run_on_startup=False, use_monitor=True)
def enviar_resumo_agenda(timer: func.TimerRequest) -> None:
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    logging.info("Timer executado em %s", utc_now.isoformat())

    today = datetime.date.today()
    agenda = _load_agenda()
    todays_items = [item for item in agenda if _is_for_today(item, today)]

    subject = f"Agenda do dia {today.strftime('%d/%m/%Y')}"
    body = _format_items(todays_items, today)

    _send_email(subject, body)
    logging.info("Resumo enviado com %d compromisso(s).", len(todays_items))
