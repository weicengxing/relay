class RegisterCodeRequest(BaseModel):
    email: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    verificationCode: str
    turnstileToken: str | None = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class CreateApiKeyRequest(BaseModel):
    name: str = Field(min_length=1)


class WebChatMessageRequest(BaseModel):
    message: str | None = ""
    newConversation: bool | None = False
    model: str | None = None
    images: list[dict[str, Any]] | None = []


class RedeemCodeRequest(BaseModel):
    code: str


class CreateNovelRequest(BaseModel):
    title: str
    author: str | None = ""
    content: str


class RateNovelRequest(BaseModel):
    score: int


class AdminRowRequest(BaseModel):
    values: dict[str, Any]


class AdminSqlRequest(BaseModel):
    sql: str


class AdminMaintenanceRequest(BaseModel):
    writeDisabled: bool


class AdminSettingImageRequest(BaseModel):
    settingKey: str
    fileName: str
    dataUrl: str


class AdminSettingImageDeleteRequest(BaseModel):
    settingKey: str


class AdminBalanceCreditRequest(BaseModel):
    email: str
    amount: Decimal


app = FastAPI(title="Relay Python Backend")
app.router.route_class = WriteGuardRoute
origins = [origin.strip() for origin in os.getenv("RELAY_PY_CORS_ORIGINS", "*").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return api_fail(exc.status, exc.code, exc.message, exc.details)


@app.exception_handler(HTTPException)
def http_error_handler(_: Request, exc: HTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return api_fail(exc.status_code, "HTTP_ERROR", message)


@app.on_event("startup")
async def startup() -> None:
    try:
        limiter = anyio.to_thread.current_default_thread_limiter()
        limiter.total_tokens = max(limiter.total_tokens, int(os.getenv("RELAY_PY_THREAD_TOKENS", "100")))
    except Exception:
        pass
    await asyncio.to_thread(init_db)
    await asyncio.to_thread(refresh_maintenance_write_disabled_cache)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return api_ok({"status": "UP", "service": "relay-backend-py", "timestamp": now_iso()})


@app.get("/api/bootstrap")
def bootstrap() -> dict[str, Any]:
    return api_ok(
        {
            "status": "ready",
            "modules": ["auth", "user", "billing", "proxy", "admin", "log", "web_chat"],
            "coreFeatures": [
                "signup",
                "login",
                "balance",
                "api_keys",
                "model_catalog",
                "chat_proxy",
                "web_chat",
                "request_logs",
                "sqlite",
            ],
            "turnstile": {
                "enabled": turnstile_enabled(),
                "siteKey": TURNSTILE_SITE_KEY,
            },
            "rechargePayment": recharge_payment_settings(),
        }
    )
