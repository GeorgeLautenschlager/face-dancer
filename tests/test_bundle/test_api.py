"""Public-API re-export test for the bundle package."""


def test_public_api_is_reexported() -> None:
    import face_dancer.bundle as bundle

    for name in ("Bundle", "BUNDLE_SCHEMA_VERSION", "BundleError", "BundleVersionError"):
        assert hasattr(bundle, name), f"bundle package does not re-export {name}"
