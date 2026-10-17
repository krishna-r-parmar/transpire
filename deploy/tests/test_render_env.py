import importlib.util
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location(
    "render_env", Path(__file__).resolve().parents[1] / "render_env.py"
)
render_env = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render_env)


class RenderEnvTests(unittest.TestCase):
    def setUp(self):
        self.settings = {
            "ENV_PARAMETER": "/transpire/qa/env",
            "CFG_APP_DOMAIN": "qa.example.com",
            "CFG_DATABASE_URL": "postgresql+asyncpg://app:encoded@db/app",
            "CFG_OUTBOX_ENCRYPTION_KEY": "existing-key",
        }

    def test_required_inputs_generate_production_defaults(self):
        request = render_env.build_request(self.settings)
        self.assertEqual(request["Type"], "SecureString")
        self.assertEqual(request["KeyId"], "alias/aws/ssm")
        self.assertIn('ENVIRONMENT="production"\n', request["Value"])
        self.assertIn('SESSION_COOKIE_SECURE="true"\n', request["Value"])
        self.assertIn('NEXT_PUBLIC_API_URL="https://qa.example.com/api/v1"\n', request["Value"])
        self.assertNotIn("your-company", request["Value"])

    def test_missing_secrets_fail_without_exposing_supplied_values(self):
        for key in ("CFG_DATABASE_URL", "CFG_OUTBOX_ENCRYPTION_KEY"):
            settings = {name: value for name, value in self.settings.items() if name != key}
            with self.assertRaises(ValueError) as raised:
                render_env.build_request(settings)
            self.assertIn(key.removeprefix("CFG_"), str(raised.exception))
            self.assertNotIn("existing-key", str(raised.exception))

    def test_domain_must_be_a_hostname(self):
        for domain in ("", "https://qa.example.com", "qa.example.com/path"):
            with self.assertRaises(ValueError):
                render_env.build_request(dict(self.settings, CFG_APP_DOMAIN=domain))

    def test_optional_override_escapes_special_characters(self):
        request = render_env.build_request(dict(
            self.settings,
            CFG_SMTP_PASSWORD='dollar$#quote"slash\\\nsecond-line',
            CFG_PUBLIC_APP_URL="https://custom.example.com",
        ))
        self.assertIn('SMTP_PASSWORD="dollar$$#quote\\"slash\\\\\\nsecond-line"\n', request["Value"])
        self.assertIn('PUBLIC_APP_URL="https://custom.example.com"\n', request["Value"])

    def test_unrelated_secrets_are_excluded(self):
        request = render_env.build_request(dict(
            self.settings, AWS_SECRET_ACCESS_KEY="excluded-value", CFG_UNKNOWN="also-excluded"
        ))
        self.assertNotIn("excluded", request["Value"])
        self.assertNotIn("APP_DOMAIN=", request["Value"])

    def test_oversized_request_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "4096-byte"):
            render_env.build_request(dict(self.settings, CFG_SMTP_PASSWORD="x" * 4097))


if __name__ == "__main__":
    unittest.main()
