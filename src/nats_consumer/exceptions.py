class DjangoNatsError(Exception):
    pass


class ConsumerNotFound(DjangoNatsError):
    def __init__(self, message="Consumer was not found - typo? Or was it not imported?"):
        super().__init__(message)
