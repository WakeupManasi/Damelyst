from fastapi import FastAPI
from app.database import supabase

app = FastAPI(
    title="SAFE Route API",
    version="1.0.0"
)


@app.get("/")
def home():
    return {
        "message": "SAFE Route Backend is running!"
    }


@app.get("/test-database")
def test_database():
    response = supabase.table("safe_routes").select("*").execute()

    return {
        "message": "Database connected successfully!",
        "data": response.data
    }