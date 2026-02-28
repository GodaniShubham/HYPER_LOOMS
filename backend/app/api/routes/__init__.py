from app.api.routes.admin import router as admin_router
from app.api.routes.credits import router as credits_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.network import router as network_router
from app.api.routes.nodes import router as nodes_router
from app.api.routes.p2p import router as p2p_router
from app.api.routes.training import router as training_router

__all__ = ["admin_router", "credits_router", "jobs_router", "network_router", "nodes_router", "p2p_router", "training_router"]
