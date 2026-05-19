use std::net::SocketAddr;
use std::sync::{Arc, Mutex};

use axum::extract::{Path, Query, State};
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use serde::Deserialize;
use tower_http::cors::CorsLayer;
use tower_http::trace::TraceLayer;

use ccusdt_exchange_sim::PaperExchange;
use ccusdt_replay_core::{ExchangeSnapshot, Fill, NewOrder, Order, ResetResponse};

#[derive(Clone)]
pub struct ApiState {
    exchange: Arc<Mutex<PaperExchange>>,
}

impl ApiState {
    pub fn new(exchange: PaperExchange) -> Self {
        Self {
            exchange: Arc::new(Mutex::new(exchange)),
        }
    }
}

#[derive(Clone, Debug, Deserialize)]
pub struct StepQuery {
    #[serde(default = "default_step_frames")]
    frames: usize,
}

fn default_step_frames() -> usize {
    1
}

#[derive(Debug)]
pub struct ApiError {
    status: StatusCode,
    message: String,
}

impl ApiError {
    fn bad_request(message: impl Into<String>) -> Self {
        Self {
            status: StatusCode::BAD_REQUEST,
            message: message.into(),
        }
    }

    fn not_found(message: impl Into<String>) -> Self {
        Self {
            status: StatusCode::NOT_FOUND,
            message: message.into(),
        }
    }

    fn internal(message: impl Into<String>) -> Self {
        Self {
            status: StatusCode::INTERNAL_SERVER_ERROR,
            message: message.into(),
        }
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        let body = serde_json::json!({ "error": self.message });
        (self.status, Json(body)).into_response()
    }
}

pub async fn serve(exchange: PaperExchange, addr: SocketAddr) -> anyhow::Result<()> {
    let app = router(ApiState::new(exchange));
    let listener = tokio::net::TcpListener::bind(addr).await?;
    tracing::info!("paper exchange listening on http://{addr}");
    axum::serve(listener, app).await?;
    Ok(())
}

pub fn router(state: ApiState) -> Router {
    Router::new()
        .route("/health", get(health))
        .route("/api/state", get(snapshot))
        .route("/api/step", post(step))
        .route("/api/reset", post(reset))
        .route("/api/orders", get(orders).post(place_order))
        .route("/api/orders/{id}/cancel", post(cancel_order))
        .route("/api/fills", get(fills))
        .layer(CorsLayer::permissive())
        .layer(TraceLayer::new_for_http())
        .with_state(state)
}

async fn health() -> Json<serde_json::Value> {
    Json(serde_json::json!({ "ok": true }))
}

async fn snapshot(State(state): State<ApiState>) -> Result<Json<ExchangeSnapshot>, ApiError> {
    let exchange = lock_exchange(&state)?;
    Ok(Json(exchange.snapshot()))
}

async fn step(
    State(state): State<ApiState>,
    Query(query): Query<StepQuery>,
) -> Result<Json<ExchangeSnapshot>, ApiError> {
    if query.frames == 0 {
        return Err(ApiError::bad_request("frames must be >= 1"));
    }
    let mut exchange = lock_exchange(&state)?;
    Ok(Json(exchange.step(query.frames)))
}

async fn reset(State(state): State<ApiState>) -> Result<Json<ResetResponse>, ApiError> {
    let mut exchange = lock_exchange(&state)?;
    exchange.reset();
    Ok(Json(ResetResponse {
        snapshot: exchange.snapshot(),
    }))
}

async fn orders(State(state): State<ApiState>) -> Result<Json<Vec<Order>>, ApiError> {
    let exchange = lock_exchange(&state)?;
    Ok(Json(exchange.orders().to_vec()))
}

async fn fills(State(state): State<ApiState>) -> Result<Json<Vec<Fill>>, ApiError> {
    let exchange = lock_exchange(&state)?;
    Ok(Json(exchange.fills().to_vec()))
}

async fn place_order(
    State(state): State<ApiState>,
    Json(request): Json<NewOrder>,
) -> Result<Json<Order>, ApiError> {
    let mut exchange = lock_exchange(&state)?;
    let order = exchange
        .place_order(request)
        .map_err(|err| ApiError::bad_request(err.to_string()))?;
    Ok(Json(order))
}

async fn cancel_order(
    State(state): State<ApiState>,
    Path(id): Path<u64>,
) -> Result<Json<Order>, ApiError> {
    let mut exchange = lock_exchange(&state)?;
    let order = exchange
        .cancel_order(id)
        .ok_or_else(|| ApiError::not_found(format!("open order {id} not found")))?;
    Ok(Json(order))
}

fn lock_exchange(state: &ApiState) -> Result<std::sync::MutexGuard<'_, PaperExchange>, ApiError> {
    state
        .exchange
        .lock()
        .map_err(|_| ApiError::internal("exchange state lock poisoned"))
}
