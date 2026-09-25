from fastapi import FastAPI, Request

gps_service = FastAPI()

@gps_service.post("/")
async def receive_location(request: Request):
    print("--- QUERY PARAMS ---")
    print(request.query_params)
    
    body = await request.body()
    print("--- RAW BODY ---")
    print(body)
    
    return {"status": "success"}
