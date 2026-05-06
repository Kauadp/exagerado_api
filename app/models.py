from sqlalchemy import Column, Integer, String, Float, DateTime, BigInteger, UniqueConstraint
from database import Base
from datetime import datetime

class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id = Column(BigInteger, primary_key=True, index=True)
    id_nota = Column(BigInteger, index=True)

    status = Column(String, default="pending")
    # pending = chegou
    # processing = sendo processado
    # done = processado 
    # error = falhou

    __table_args__ = (
        UniqueConstraint('id_nota', name='unique_id_nota'),
    )

    tentativas = Column(Integer, default=0)
    
    criado_em = Column(DateTime, default=datetime.utcnow)

class VendaItem(Base):
    __tablename__ = "vendas_itens"
    id = Column(Integer, primary_key=True, index=True)
    venda_id = Column(BigInteger, index=True)
    id_loja = Column(BigInteger)
    produto_id = Column(String)
    sku = Column(String)
    linha = Column(Integer, default=0)        # ← novo
    nome_produto = Column(String)
    quantidade = Column(Float)
    valor_unitario = Column(Float)
    valor_total = Column(Float)
    estoque_pos_venda = Column(Float)
    timestamp = Column(DateTime)

    __table_args__ = (
        UniqueConstraint('venda_id', 'sku', 'linha', name='unique_venda_item'),
    )
