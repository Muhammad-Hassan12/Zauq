def execution_permission(profile: dict | None, default_mode: str = 'hangout') -> bool:
    """Configured permission wins; mode supplies only an unset default."""
    if profile and profile.get('allow_code_exec') is not None:
        return bool(profile['allow_code_exec'])
    return (profile or {}).get('operating_mode', default_mode) == 'dev'
