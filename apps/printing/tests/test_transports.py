"""Pins the transport seam. No sockets are opened anywhere in this file.

Invariants this file exists to protect:

1. Moving a household from the LAN broker to Bambu's cloud broker is a value
   change on ``PrinterProfile.transport`` — ``build_transport`` is the only
   place that knows the difference, and it returns the right class for each.
2. The LAN transport's TLS policy is deliberately relaxed and deliberately
   specific: user ``bblp``, the printer's access code as the password,
   ``check_hostname=False`` (the certificate's CN is the *serial*, not the IP
   you dial), and TLS capped at 1.2 (some firmware never answers a 1.3
   ClientHello).
3. The cloud transport verifies TLS **fully** — public CA, matching CN. This
   is a real security property, not an accident, and it must not inherit the
   local transport's relaxed policy.
4. Missing credentials fail loudly, naming the printer, so the supervisor can
   surface which printer needs attention.
5. Both transports address the same topics: ``device/<serial>/report`` and
   ``device/<serial>/request``.
6. Credentials round-trip through Fernet, a partial update merges rather than
   wiping, and an undecryptable blob degrades to ``{}`` instead of raising —
   a rotated ``SECRET_KEY`` must not take down the supervisor loop.
7. ``request_full_status`` publishes the exact ``pushall`` payload. Reports
   are deltas, so this is the only way a listener that connects mid-print
   ever learns ``subtask_name``.
"""
from __future__ import annotations

from django.test import TestCase, override_settings

from apps.printing.models import PrinterProfile
from apps.printing.transports import (
    CloudMqttTransport,
    InMemoryTransport,
    LocalMqttTransport,
    TransportConfig,
    TransportError,
    build_cloud_config,
    build_local_config,
    build_transport,
)
from config.tests.factories import make_family

ACCESS_CODE = "12345678"
CLOUD_TOKEN = "eyJhbGciOiJIUzI1NiJ9.super-secret-access-token"


class _Fixture(TestCase):
    def setUp(self):
        self.household = make_family(
            "Household",
            parents=[{"username": "parent"}],
            children=[{"username": "kid"}],
        )

    def make_printer(self, *, transport=PrinterProfile.Transport.LOCAL,
                     secrets=None, **kwargs):
        defaults = {
            "family": self.household.family,
            "name": "Garage X1C",
            "serial": "00M09A000000001",
            "host": "192.168.1.50",
            "transport": transport,
        }
        defaults.update(kwargs)
        printer = PrinterProfile(**defaults)
        if secrets:
            printer.set_secrets(**secrets)
        printer.save()
        return printer


class BuildTransportTests(_Fixture):
    def test_local_transport_builds_a_local_mqtt_client(self):
        printer = self.make_printer(secrets={"access_code": ACCESS_CODE})
        transport = build_transport(printer, on_payload=lambda payload: None)
        self.assertIsInstance(transport, LocalMqttTransport)

    def test_cloud_transport_builds_a_cloud_mqtt_client(self):
        printer = self.make_printer(
            transport=PrinterProfile.Transport.CLOUD,
            secrets={"cloud_user_id": "1234567", "cloud_token": CLOUD_TOKEN},
        )
        transport = build_transport(printer, on_payload=lambda payload: None)
        self.assertIsInstance(transport, CloudMqttTransport)

    def test_swapping_the_transport_value_is_the_whole_migration(self):
        # The "config change, not a rewrite" guarantee, asserted directly:
        # the same profile, with one field changed, yields the other client.
        printer = self.make_printer(secrets={
            "access_code": ACCESS_CODE,
            "cloud_user_id": "1234567",
            "cloud_token": CLOUD_TOKEN,
        })
        self.assertIsInstance(
            build_transport(printer, on_payload=lambda p: None), LocalMqttTransport,
        )
        printer.transport = PrinterProfile.Transport.CLOUD
        printer.save(update_fields=["transport"])
        self.assertIsInstance(
            build_transport(printer, on_payload=lambda p: None), CloudMqttTransport,
        )

    def test_an_unrecognised_transport_names_the_printer(self):
        printer = self.make_printer(secrets={"access_code": ACCESS_CODE})
        printer.transport = "carrier-pigeon"
        with self.assertRaises(TransportError) as ctx:
            build_transport(printer, on_payload=lambda p: None)
        self.assertIn("Garage X1C", str(ctx.exception))


class LocalConfigTests(_Fixture):
    def setUp(self):
        super().setUp()
        self.printer = self.make_printer(secrets={"access_code": ACCESS_CODE})

    def test_username_is_the_literal_bblp(self):
        self.assertEqual(build_local_config(self.printer).username, "bblp")

    def test_password_is_the_stored_access_code(self):
        self.assertEqual(build_local_config(self.printer).password, ACCESS_CODE)

    def test_hostname_checking_is_off_because_the_cn_is_the_serial(self):
        # The printer's self-signed certificate has CN=<serial>, and we dial
        # 192.168.x.x — a hostname check can never pass.
        self.assertFalse(build_local_config(self.printer).check_hostname)

    def test_tls_is_capped_at_1_2(self):
        self.assertEqual(build_local_config(self.printer).max_tls_version, "1.2")

    def test_host_and_port_come_from_the_profile(self):
        config = build_local_config(self.printer)
        self.assertEqual(config.host, "192.168.1.50")
        self.assertEqual(config.port, 8883)
        self.assertEqual(config.serial, "00M09A000000001")

    def test_chain_verification_is_off_without_a_vendored_ca(self):
        with override_settings(PRINT_BAMBU_CA_CERT=""):
            config = build_local_config(self.printer)
        self.assertFalse(config.verify_tls)
        self.assertEqual(config.ca_cert_path, "")

    def test_chain_verification_turns_on_when_a_ca_is_configured(self):
        with override_settings(PRINT_BAMBU_CA_CERT="/etc/ssl/bambu-ca.pem"):
            config = build_local_config(self.printer)
        self.assertTrue(config.verify_tls)
        self.assertEqual(config.ca_cert_path, "/etc/ssl/bambu-ca.pem")
        # Still never the hostname, even with a verified chain.
        self.assertFalse(config.check_hostname)

    def test_a_missing_access_code_raises_and_names_the_printer(self):
        bare = self.make_printer(name="Basement P1S", serial="00M09A000000002")
        with self.assertRaises(TransportError) as ctx:
            build_local_config(bare)
        self.assertIn("Basement P1S", str(ctx.exception))

    def test_a_missing_lan_address_raises_and_names_the_printer(self):
        hostless = self.make_printer(
            name="Attic X1E", serial="00M09A000000003", host="",
            secrets={"access_code": ACCESS_CODE},
        )
        with self.assertRaises(TransportError) as ctx:
            build_local_config(hostless)
        self.assertIn("Attic X1E", str(ctx.exception))


class CloudConfigTests(_Fixture):
    def setUp(self):
        super().setUp()
        self.printer = self.make_printer(
            transport=PrinterProfile.Transport.CLOUD,
            secrets={"cloud_user_id": "1234567", "cloud_token": CLOUD_TOKEN},
        )

    def test_username_is_u_underscore_uid(self):
        self.assertEqual(build_cloud_config(self.printer).username, "u_1234567")

    def test_password_is_the_access_token_verbatim(self):
        # No "Bearer " prefix — the broker wants the raw token.
        self.assertEqual(build_cloud_config(self.printer).password, CLOUD_TOKEN)

    def test_host_comes_from_settings(self):
        with override_settings(PRINT_BAMBU_CLOUD_HOST="cn.mqtt.bambulab.com"):
            self.assertEqual(
                build_cloud_config(self.printer).host, "cn.mqtt.bambulab.com",
            )

    def test_tls_is_fully_verified_on_the_cloud_broker(self):
        # A real security property: the cloud certificate is DigiCert-issued
        # with a CN that matches the host, so both checks are correct here and
        # must NOT inherit the local transport's relaxed policy.
        config = build_cloud_config(self.printer)
        self.assertTrue(config.verify_tls)
        self.assertTrue(config.check_hostname)
        self.assertEqual(config.ca_cert_path, "")
        self.assertEqual(config.max_tls_version, "")

    def test_a_missing_uid_or_token_raises_and_names_the_printer(self):
        for secrets in (
            {"cloud_user_id": "1234567"},
            {"cloud_token": CLOUD_TOKEN},
            {},
        ):
            with self.subTest(secrets=secrets):
                printer = PrinterProfile(
                    family=self.household.family,
                    name="Studio X1C",
                    serial="00M09A00000009",
                    transport=PrinterProfile.Transport.CLOUD,
                )
                if secrets:
                    printer.set_secrets(**secrets)
                with self.assertRaises(TransportError) as ctx:
                    build_cloud_config(printer)
                self.assertIn("Studio X1C", str(ctx.exception))


class TopicTests(TestCase):
    def test_both_transports_address_the_same_topics(self):
        for label, config in (
            ("local", TransportConfig(serial="00M09A000000001", host="192.168.1.50")),
            ("cloud", TransportConfig(
                serial="00M09A000000001", host="us.mqtt.bambulab.com",
            )),
        ):
            with self.subTest(transport=label):
                self.assertEqual(config.report_topic, "device/00M09A000000001/report")
                self.assertEqual(config.request_topic, "device/00M09A000000001/request")


class SecretStorageTests(_Fixture):
    def test_secrets_round_trip_through_fernet(self):
        printer = self.make_printer(secrets={
            "access_code": ACCESS_CODE, "cloud_token": CLOUD_TOKEN,
        })
        printer.refresh_from_db()
        self.assertEqual(
            printer.get_secrets(),
            {"access_code": ACCESS_CODE, "cloud_token": CLOUD_TOKEN},
        )

    def test_the_ciphertext_does_not_contain_the_plaintext(self):
        printer = self.make_printer(secrets={"access_code": ACCESS_CODE})
        printer.refresh_from_db()
        self.assertNotIn(ACCESS_CODE.encode(), bytes(printer.encrypted_secret))

    def test_a_partial_update_merges_instead_of_wiping(self):
        printer = self.make_printer(secrets={
            "access_code": ACCESS_CODE, "cloud_user_id": "1234567",
        })
        # A PATCH that only renames the printer passes None for the omitted
        # credentials; they must survive.
        printer.set_secrets(access_code=None, cloud_user_id=None,
                            cloud_token=CLOUD_TOKEN)
        printer.save()
        printer.refresh_from_db()
        self.assertEqual(printer.get_secrets(), {
            "access_code": ACCESS_CODE,
            "cloud_user_id": "1234567",
            "cloud_token": CLOUD_TOKEN,
        })

    def test_an_explicit_empty_string_clears_one_credential(self):
        printer = self.make_printer(secrets={"access_code": ACCESS_CODE})
        printer.set_secrets(access_code="")
        printer.save()
        printer.refresh_from_db()
        self.assertEqual(printer.get_secrets(), {"access_code": ""})

    def test_an_undecryptable_blob_reads_as_empty_rather_than_raising(self):
        # This is what a rotated SECRET_KEY looks like. The supervisor must
        # skip that printer, not crash the loop for every other printer.
        printer = self.make_printer(secrets={"access_code": ACCESS_CODE})
        PrinterProfile.objects.filter(pk=printer.pk).update(
            encrypted_secret=b"this-is-not-a-fernet-token",
        )
        printer.refresh_from_db()
        self.assertEqual(printer.get_secrets(), {})

    def test_an_unset_blob_reads_as_empty(self):
        printer = self.make_printer()
        printer.refresh_from_db()
        self.assertEqual(printer.get_secrets(), {})


class HasCredentialsTests(_Fixture):
    def test_local_needs_both_an_access_code_and_a_host(self):
        self.assertFalse(self.make_printer().has_credentials)
        self.assertFalse(
            self.make_printer(
                serial="00M09A000000002", host="", secrets={"access_code": ACCESS_CODE},
            ).has_credentials,
        )
        self.assertTrue(
            self.make_printer(
                serial="00M09A000000003", secrets={"access_code": ACCESS_CODE},
            ).has_credentials,
        )

    def test_cloud_needs_both_a_uid_and_a_token(self):
        self.assertFalse(
            self.make_printer(
                serial="00M09A000000004",
                transport=PrinterProfile.Transport.CLOUD,
                secrets={"cloud_user_id": "1234567"},
            ).has_credentials,
        )
        self.assertTrue(
            self.make_printer(
                serial="00M09A000000005",
                transport=PrinterProfile.Transport.CLOUD,
                secrets={"cloud_user_id": "1234567", "cloud_token": CLOUD_TOKEN},
            ).has_credentials,
        )


class InMemoryTransportTests(TestCase):
    def test_request_full_status_publishes_the_exact_pushall_payload(self):
        transport = InMemoryTransport(on_payload=lambda payload: None)
        transport.request_full_status()
        self.assertEqual(transport.published, [{
            "pushing": {
                "sequence_id": "0",
                "command": "pushall",
                "version": 1,
                "push_target": 1,
            },
        }])

    def test_feed_delivers_payloads_to_the_handler(self):
        seen = []
        transport = InMemoryTransport(on_payload=seen.append)
        transport.feed_all([{"a": 1}, {"b": 2}])
        self.assertEqual(seen, [{"a": 1}, {"b": 2}])

    def test_start_and_stop_report_their_status(self):
        states = []
        transport = InMemoryTransport(
            on_payload=lambda payload: None,
            on_status=lambda state, detail: states.append(state),
        )
        transport.start()
        self.assertTrue(transport.started)
        transport.stop()
        self.assertFalse(transport.started)
        self.assertEqual(states, ["connected", "disconnected"])
