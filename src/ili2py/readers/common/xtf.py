def model_names_from_transfer(transfer):
    headersection = getattr(transfer, "HEADERSECTION", None)
    if headersection is not None:
        return [model.NAME for model in headersection.MODELS]

    headersection = getattr(transfer, "headersection", None)
    if headersection is None:
        return []
    models = getattr(headersection, "models", None)
    if models is None:
        return []
    return [model.model for model in getattr(models, "elements", [])]
