import pytest
import asyncio
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base
from app.main import app,get_db
@pytest.fixture
def db():
 e=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool); Base.metadata.create_all(e)
 with sessionmaker(bind=e,expire_on_commit=False)() as s: yield s
 e.dispose()
@pytest.fixture
def client(db):
 async def override(): yield db
 app.dependency_overrides[get_db]=override
 class Client:
  def get(self,path):
   async def request():
    transport=httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport,base_url="http://testserver") as c:
     return await c.get(path)
   return asyncio.run(request())
 yield Client()
 app.dependency_overrides.clear()
