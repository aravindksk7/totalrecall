from totalrecall.config.credentials import CredentialProviderChain
from totalrecall.config.runtime_flags import RuntimeFeatureFlagProvider
from totalrecall.config.settings import Settings
from totalrecall.main import create_app


def test_create_app_wires_external_credential_provider_when_configured() -> None:
    app = create_app(
        Settings(
            enable_database=False,
            feature_flags={"memory.adapter": "stub"},
            credential_refs={"api_key": "external:api-key"},
            external_credential_base_url="https://secrets.example.test",
        )
    )

    assert isinstance(app.state.credential_provider, CredentialProviderChain)


def test_create_app_wires_external_feature_flag_provider_when_configured() -> None:
    app = create_app(
        Settings(
            enable_database=False,
            feature_flags={"memory.adapter": "stub"},
            external_feature_flags_url="https://flags.example.test/openfeature",
        )
    )

    assert isinstance(app.state.feature_flags, RuntimeFeatureFlagProvider)
