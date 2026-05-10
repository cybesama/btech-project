from typing import List

from backend.config import config


def send_sos_sms(contacts: List[dict], lat: float, lng: float) -> List[str]:
    """Send an SOS SMS to all emergency contacts. Returns a list of outcome strings."""
    if not config.TWILIO_ACCOUNT_SID or not config.TWILIO_AUTH_TOKEN:
        return ["Twilio is not configured — add credentials to .env"]

    from twilio.rest import Client  # lazy import so startup isn't blocked when unconfigured

    client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    maps_link = f"https://maps.google.com/?q={lat},{lng}"
    body = (
        f"EMERGENCY SOS from {config.USER_NAME}.\n"
        f"Location: {maps_link}\n"
        f"Please respond immediately."
    )

    outcomes = []
    for contact in contacts:
        try:
            client.messages.create(
                body=body,
                from_=config.TWILIO_PHONE_NUMBER,
                to=contact["phone"],
            )
            outcomes.append(f"Sent to {contact['name']}")
        except Exception as exc:
            outcomes.append(f"Failed ({contact['name']}): {exc}")

    return outcomes
