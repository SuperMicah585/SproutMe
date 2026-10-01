import os
import logging
import phonenumbers
from twilio.rest import Client as TwilioClient

logger = logging.getLogger(__name__)


class TwilioVerificationManager:
    def __init__(self):
        self.account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
        self.auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
        self.verify_service_sid = os.environ.get("TWILIO_VERIFY_SERVICE_SID")
        self.client = TwilioClient(self.account_sid, self.auth_token)

    def is_valid_phone_number(self, phone_number, region="US"):
        try:
            parsed = phonenumbers.parse(phone_number, region)
            valid = phonenumbers.is_valid_number(parsed)
            formatted = phonenumbers.format_number(
                parsed, phonenumbers.PhoneNumberFormat.E164
            )
            return {"valid": valid, "formatted_number": formatted}
        except Exception:
            return {"valid": False, "formatted_number": phone_number}

    def send_verification(self, phone_number):
        if not phone_number or not self.verify_service_sid:
            logger.error("Missing phone number or TWILIO_VERIFY_SERVICE_SID")
            return False
        try:
            self.client.verify.v2.services(self.verify_service_sid).verifications.create(
                to=phone_number,
                channel="sms",
            )
            return True
        except Exception:
            logger.exception("send_verification failed")
            return False

    def verify_code(self, phone_number, verification_code):
        if not phone_number or not verification_code or not self.verify_service_sid:
            return False
        try:
            check = self.client.verify.v2.services(self.verify_service_sid).verification_checks.create(
                to=phone_number,
                code=verification_code,
            )
            return check.status == "approved"
        except Exception:
            logger.exception("verify_code failed")
            return False
