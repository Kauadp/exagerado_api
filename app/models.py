from sqlalchemy import Column, Integer, String, Float, DateTime, BigInteger
from .database import Base

class VendaItem(Base):
    __tablename__ = "vendas_itens"

    id = Column(Integer, primary_key=True, index=True)
    venda_id = Column(BigInteger, index=True)
    id_loja = Column(BigInteger)
    produto_id = Column(BigInteger, index=True)
    sku = Column(String)
    nome_produto = Column(String)
    quantidade = Column(Float)
    valor_unitario = Column(Float)
    valor_total = Column(Float)
    estoque_pos_venda = Column(Float)
    timestamp = Column(DateTime)