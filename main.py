from fastapi import FastAPI

app = FastAPI(title="My Local API")

# test GEt endpoijt if the server is alive
@app.get("/")
def read_root():
    return {"message": "FastAPI is running locally!"}

@app.get("/items/{item_id}")
def read_item(item_id: int):
    return {"item_id": item_id, "name": f"Item number {item_id}"}

@app.post("/items/")
def create_item(name: str, price: float):
    # just returns what you sent back as a confirmation
    return {"created": True, "item_name": name, "price": price}
