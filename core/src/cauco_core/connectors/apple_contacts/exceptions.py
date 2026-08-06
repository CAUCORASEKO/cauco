"""Safe Apple Contacts connector errors."""


class AppleContactsError(RuntimeError):
    """Base connector error."""


class ContactsPlatformUnsupportedError(AppleContactsError):
    pass


class ContactsNativeBridgeUnavailableError(AppleContactsError):
    pass


class ContactsPermissionError(AppleContactsError):
    pass


class ContactsInvalidQueryError(AppleContactsError):
    pass


class ContactNotFoundError(AppleContactsError):
    pass
