"""Factory for building a JiraAdapterProtocol from feature flags and credentials."""

from totalrecall.config.credentials import CredentialNotFoundError, CredentialProvider
from totalrecall.config.feature_flags import FeatureFlagProvider
from totalrecall.testgen.jira.adapter import (
    JiraAdapterProtocol,
    JiraCloudAdapter,
    NullJiraAdapter,
    StubJiraAdapter,
)


def build_jira_adapter(
    feature_flags: FeatureFlagProvider,
    credential_provider: CredentialProvider,
) -> JiraAdapterProtocol:
    if not feature_flags.get_bool("jira.enabled", False):
        return NullJiraAdapter()

    adapter_name = feature_flags.get_string("jira.adapter", "cloud")
    if adapter_name == "stub":
        return StubJiraAdapter()

    base_url = feature_flags.get_string("jira.base_url", "")
    email = feature_flags.get_string("jira.email", "")
    if not base_url or not email:
        return NullJiraAdapter()

    try:
        api_token = credential_provider.get("jira_api_token")
    except CredentialNotFoundError:
        return NullJiraAdapter()

    timeout = int(feature_flags.get_string("jira.timeout_seconds", "10"))
    return JiraCloudAdapter(
        base_url=base_url,
        email=email,
        api_token=api_token,
        timeout_seconds=timeout,
    )
