from app.backend.services.chroma_runtime import (
    similarity_query,
    smart_comms_collection,
    upsert_document,
)


def index_smart_comms_memory(
    order_id: str,
    customer_name: str,
    route_label: str,
    operator_question: str,
    assistant_response: str,
) -> None:
    document = (
        f"Customer: {customer_name}. "
        f"Route: {route_label}. "
        f"Operator asked: {operator_question}. "
        f"Assistant responded: {assistant_response}."
    )
    upsert_document(
        collection_name="smart_comms_memory",
        document_id=f"scm_{order_id}",
        document=document,
        metadata={
            "order_id": order_id,
            "customer_name": customer_name,
            "route_label": route_label,
        },
    )


def retrieve_smart_comms_context(
    query: str,
    top_k: int = 3,
) -> list[dict]:
    return similarity_query(
        collection_name="smart_comms_memory",
        query=query,
        top_k=top_k,
    )


def index_carrier_decision_memory(
    order_id: str,
    origin: str,
    destination: str,
    adr_required: bool,
    truck_type: str,
    customer_price: str,
    selected_carrier: str,
    carrier_price: str,
    margin: str,
) -> None:
    document = (
        f"Route: {origin} to {destination}. "
        f"ADR: {'yes' if adr_required else 'no'}. "
        f"Truck: {truck_type}. "
        f"Customer price: {customer_price}. "
        f"Selected carrier: {selected_carrier} at {carrier_price}. "
        f"Margin: {margin}."
    )
    upsert_document(
        collection_name="carrier_search_memory",
        document_id=f"cs_{order_id}",
        document=document,
        metadata={
            "order_id": order_id,
            "origin": origin,
            "destination": destination,
            "adr_required": adr_required,
            "selected_carrier": selected_carrier,
        },
    )


def retrieve_carrier_search_context(
    query: str,
    top_k: int = 3,
) -> list[dict]:
    return similarity_query(
        collection_name="carrier_search_memory",
        query=query,
        top_k=top_k,
    )
