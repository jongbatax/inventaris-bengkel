from .models import ProgramKeahlian


class ProgramFilterMiddleware:
    """Filter per jurusan (Program Keahlian) untuk Waka. Sarpras & admin; disimpan di session."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        u = request.user
        u.program_filter = None
        if u.is_authenticated and can_filter_program(u):
            pid = request.session.get("program_filter")
            if pid:
                u.program_filter = ProgramKeahlian.objects.filter(pk=pid).first()
        return self.get_response(request)


def can_filter_program(user):
    p = getattr(user, "profile", None)
    return user.is_superuser or bool(p and p.role == "wakasarpras")


def program_context(request):
    u = request.user
    if u.is_authenticated and can_filter_program(u):
        return {"program_choices": ProgramKeahlian.objects.all(),
                "program_active": getattr(u, "program_filter", None)}
    return {}
