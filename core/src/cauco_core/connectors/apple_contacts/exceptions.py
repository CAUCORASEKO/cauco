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


class ContactsNativeError(AppleContactsError):
    """The native Contacts bridge failed safely."""


class ContactsPermissionTimeoutError(ContactsNativeError):
    """The native permission callback did not arrive in time."""


class ContactsPermissionRequestError(ContactsNativeError):
    """The native permission request failed."""
