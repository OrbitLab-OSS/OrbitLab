"""Tests for operator-facing appliance input boundaries."""

from orbitlab.domain.appliances import ApplianceNetworkProfile, BootstrapDocument


def test_bootstrap_document_is_structured_base64_json() -> None:
    document = BootstrapDocument("gateway", "olvn100", {"domain": "lab.example", "dhcp": True})

    assert document.encode() == "eyJraW5kIjoiZ2F0ZXdheSIsInJlc291cmNlX2lkIjoib2x2bjEwMCIsInZhbHVlcyI6eyJkaGNwIjp0cnVlLCJkb21haW4iOiJsYWIuZXhhbXBsZSJ9fQ=="


def test_network_profile_rejects_invalid_guest_agent_requirement() -> None:
    profile = ApplianceNetworkProfile("DockFS", nic_count=1, supports_dhcp=True, requires_guest_agent=True)

    try:
        profile.validate(network="10.20.0.0/24", mtu=1450, nic_count=1, dhcp_enabled=True, guest_agent=False)
    except ValueError as error:
        assert str(error) == "DockFS requires the Proxmox guest agent."
    else:
        raise AssertionError("Expected a validation error")
