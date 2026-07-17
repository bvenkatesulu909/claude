"""Agent registry — all seven agents, every one a LangGraph StateGraph."""
from agents.planning import PlanningAgent
from agents.research import ResearchAgent
from agents.manufacturing import ManufacturingAgent
from agents.accounting import AccountingAgent
from agents.trading import TradingAgent
from agents.retailer import RetailerAgent
from agents.business import BusinessAgent


AGENTS = {
    a.name: a
    for a in [
        PlanningAgent(),
        ResearchAgent(),
        ManufacturingAgent(),
        TradingAgent(),
        AccountingAgent(),
        BusinessAgent(),
        RetailerAgent(),
    ]
}


def list_agents():
    return [
        {
            "name": a.name,
            "title": a.title,
            "description": a.description,
            "live": a.live,
            "framework": a.framework,
        }
        for a in AGENTS.values()
    ]


def get_agent(name: str):
    return AGENTS.get(name)
