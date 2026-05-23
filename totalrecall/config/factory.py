from totalrecall.config.credentials import (
    CredentialProvider,
    CredentialProviderChain,
    EnvLocalCredentialProvider,
    ExternalCredentialProvider,
)
from totalrecall.config.feature_flags import (
    ConfigFeatureFlagProvider,
    ExternalFeatureFlagProvider,
    FeatureFlagProvider,
)
from totalrecall.config.settings import Settings


def build_feature_flag_provider(settings: Settings) -> FeatureFlagProvider:
    config_provider = ConfigFeatureFlagProvider(settings.feature_flags)
    if not settings.external_feature_flags_url:
        return config_provider

    return ExternalFeatureFlagProvider(
        settings.external_feature_flags_url,
        fallback=config_provider,
        auth_token=settings.external_feature_flags_auth_token,
        timeout_seconds=settings.external_feature_flags_timeout_seconds,
        cache_ttl_seconds=settings.external_feature_flags_cache_ttl_seconds,
    )


def build_credential_provider(settings: Settings) -> CredentialProvider:
    env_local_provider = EnvLocalCredentialProvider(
        credential_refs=settings.credential_refs,
        local_secrets_dir=settings.local_secrets_dir,
    )
    if not settings.external_credential_base_url:
        return env_local_provider

    return CredentialProviderChain(
        [
            env_local_provider,
            ExternalCredentialProvider(
                credential_refs=settings.credential_refs,
                base_url=settings.external_credential_base_url,
                auth_token=settings.external_credential_auth_token,
                timeout_seconds=settings.external_credential_timeout_seconds,
            ),
        ]
    )
