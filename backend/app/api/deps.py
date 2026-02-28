from starlette.requests import HTTPConnection

from app.core.config import Settings
from app.services.credit_ledger import CreditLedger
from app.services.orchestrator import JobOrchestrator
from app.services.p2p_overlay import P2POverlayService
from app.services.state_store import InMemoryStateStore
from app.services.training_metadata_store import TrainingMetadataStore
from app.services.training_orchestrator import TrainingOrchestrator
from app.ws.hub import WebSocketHub


def get_settings(connection: HTTPConnection) -> Settings:
    return connection.app.state.settings


def get_store(connection: HTTPConnection) -> InMemoryStateStore:
    return connection.app.state.store


def get_orchestrator(connection: HTTPConnection) -> JobOrchestrator:
    return connection.app.state.orchestrator


def get_hub(connection: HTTPConnection) -> WebSocketHub:
    return connection.app.state.ws_hub


def get_credit_ledger(connection: HTTPConnection) -> CreditLedger:
    return connection.app.state.credit_ledger


def get_p2p_overlay(connection: HTTPConnection) -> P2POverlayService:
    return connection.app.state.p2p_overlay


def get_training_metadata_store(connection: HTTPConnection) -> TrainingMetadataStore:
    return connection.app.state.training_metadata_store


def get_training_orchestrator(connection: HTTPConnection) -> TrainingOrchestrator:
    return connection.app.state.training_orchestrator
