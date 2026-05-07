import pandas as pd
from datetime import datetime, timedelta
from babel.dates import format_date

class AlertaBase:
    def __init__(self, df_loja, loja_id):
        self.df = df_loja
        self.loja_id = loja_id

    def analisar(self):
        """Sobrescrevível: lógica matemática aqui"""
        pass

    def gerar_texto(self):
        """Sobrescrevível: formatação da string aqui"""
        pass


class AlertaPerformance(AlertaBase):
    def analisar(self):
        agora = datetime.now()
        
        # Última hora COMPLETA (ex: se são 12:47, pega 11:00-12:00)
        hora_atual = agora.replace(minute=0, second=0, microsecond=0)
        hora_anterior = hora_atual - timedelta(hours=1)
        ontem_hora_anterior = hora_anterior - timedelta(days=1)
        ontem_hora_atual = hora_atual - timedelta(days=1)

        # Última hora completa — hoje
        self.venda_ultima_hora = self.df[
            (self.df["timestamp"] >= hora_anterior) &
            (self.df["timestamp"] < hora_atual)
        ]["valor_total"].sum()

        self.pecas_ultima_hora = self.df[
            (self.df["timestamp"] >= hora_anterior) &
            (self.df["timestamp"] < hora_atual)
        ]["quantidade"].sum()

        # Mesma hora — ontem
        self.venda_ontem_hora = self.df[
            (self.df["timestamp"] >= ontem_hora_anterior) &
            (self.df["timestamp"] < ontem_hora_atual)
        ]["valor_total"].sum()

        # Totais do dia (meia-noite até agora)
        inicio_hoje = agora.replace(hour=0, minute=0, second=0, microsecond=0)
        inicio_ontem = inicio_hoje - timedelta(days=1)
        fim_ontem = inicio_hoje

        self.faturamento_total_hoje = self.df[
            self.df["timestamp"] >= inicio_hoje
        ]["valor_total"].sum()

        self.pecas_total_hoje = self.df[
            self.df["timestamp"] >= inicio_hoje
        ]["quantidade"].sum()

        self.faturamento_total_ontem = self.df[
            (self.df["timestamp"] >= inicio_ontem) &
            (self.df["timestamp"] < fim_ontem)
        ]["valor_total"].sum()

        # Variação da última hora
        if self.venda_ontem_hora > 0:
            self.variacao_hora = (self.venda_ultima_hora / self.venda_ontem_hora) - 1
        else:
            self.variacao_hora = 0

    def gerar_texto(self):
        agora = datetime.now()
        hora_anterior = agora.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
        dia_semana_ontem = format_date(agora - timedelta(days=1), format='EEEE', locale='pt_BR')
        hora_str = f"{hora_anterior.strftime('%H')}h-{agora.strftime('%H')}h"

        emoji = "📈" if self.variacao_hora >= 0 else "📉"
        sinal = "+" if self.variacao_hora >= 0 else ""

        return (
            f"🕐 *{hora_str}*\n\n"
            f"*Última hora*\n"
            f"• Hoje: R$ {self.venda_ultima_hora:,.2f} | {int(self.pecas_ultima_hora)} pçs\n"
            f"• {dia_semana_ontem}: R$ {self.venda_ontem_hora:,.2f}\n"
            f"{emoji} Variação: {sinal}{self.variacao_hora:.1%}\n\n"
            f"*Acumulado hoje*\n"
            f"• Faturamento: R$ {self.faturamento_total_hoje:,.2f}\n"
            f"• Peças: {int(self.pecas_total_hoje)} pçs\n"
            f"• Ontem total: R$ {self.faturamento_total_ontem:,.2f}"
        )
    
class AlertaRanking(AlertaBase):
    def analisar(self):
        agora = datetime.now()
        uma_hora_atras = agora - timedelta(hours=1)
        
        # Filtra apenas as vendas da última hora para esta loja
        df_hora = self.df[
            (self.df['timestamp'] >= uma_hora_atras) & 
            (self.df['timestamp'] <= agora)
        ]
        
        if not df_hora.empty:
            # Agrupa por produto e soma a quantidade vendida
            self.ranking = (
                df_hora.groupby('nome_produto')['quantidade']
                .sum()
                .sort_values(ascending=False)
                .head(3) # Pega o Top 3
            )
        else:
            self.ranking = pd.Series()

    def gerar_texto(self):
        if self.ranking.empty:
            return None # Não envia nada se não houve vendas na hora
            
        msg = "🔥 *Destaques da Última Hora*\n\n"
        msg += "Os produtos abaixo estão com alta saída. Verifique a vitrine e a reposição:\n\n"
        
        for i, (produto, qtd) in enumerate(self.ranking.items(), 1):
            msg += f"{i}º. *{produto}* ({int(qtd)} unidades)\n"
            
        msg += "\n💡 _Dica: Considere dar mais destaque visual a esses itens._"
        return msg
    
class AlertaLogistica(AlertaBase):
    def analisar(self):
        agora = datetime.now()
        uma_hora_atras = agora - timedelta(hours=1)
        inicio_evento = self.df['timestamp'].min()
        
        # Velocidade na Última Hora (Vendas/Hora)
        df_hora = self.df[self.df['timestamp'] >= uma_hora_atras]
        vendas_hora = df_hora.groupby('nome_produto')['quantidade'].sum()
        
        # Velocidade Média do Evento (Até agora)
        horas_decorridas = (agora - inicio_evento).total_seconds() / 3600
        vendas_totais = self.df.groupby('nome_produto')['quantidade'].sum()
        vel_media = vendas_totais / horas_decorridas
        
        # Identificar produtos críticos
        self.criticos = []
        estoque_atual = self.df.groupby('nome_produto')['estoque_pos_venda'].last()
        
        for produto in vendas_hora.index:
            v_atual = vendas_hora[produto]
            v_media = vel_media.get(produto, 0)
            estoque = estoque_atual.get(produto, 0)
            
            # Regra: Se vendendo 40% acima da média OU estoque dura menos de 2h
            if v_atual > (v_media * 1.4) or (estoque < (v_atual * 2)):
                tempo_restante = (estoque / v_atual) if v_atual > 0 else 99
                self.criticos.append({
                    'nome': produto,
                    'v_atual': v_atual,
                    'v_media': v_media,
                    'estoque': estoque,
                    'horas_restantes': tempo_restante
                })

    def gerar_texto(self):
        if not self.criticos: return None
        
        msg = "🚛 *ALERTA DE LOGÍSTICA PREDITIVA*\n\n"
        for p in self.criticos:
            msg += f"📦 *{p['nome']}*\n"
            msg += f"• Ritmo: {int(p['v_atual'])} un/h (Média: {int(p['v_media'])} un/h)\n"
            msg += f"• Estoque: {int(p['estoque'])} un (Dura ~{p['horas_restantes']:.1f}h)\n"
            msg += "⚠️ _Providencie reabastecimento logo!_\n\n"
        return msg
    
class AlertaBayes(AlertaBase):
    def analisar(self):
        df_loja = self.df.copy()        
        carrinhos = df_loja.groupby('venda_id')['nome_produto'].apply(list)
        
        carrinhos_multiples = carrinhos[carrinhos.str.len() > 1]
        
        self.insights = []
        if len(carrinhos_multiples) < 5: return # Evita estatística com poucos dados

        produtos = df_loja['nome_produto'].unique()
        
        for prod_a in produtos:
            count_a = sum(1 for c in carrinhos if prod_a in c)
            if count_a < 3: continue # Ignora produtos que venderam muito pouco

            for prod_b in produtos:
                if prod_a == prod_b: continue
                
                count_a_e_b = sum(1 for c in carrinhos_multiples if prod_a in c and prod_b in c)
                
                # P(B|A) = P(A e B) / P(A)
                prob_condicional = count_a_e_b / count_a
                
                if prob_condicional >= 0.5: # Threshold de 50%
                    self.insights.append({
                        'base': prod_a,
                        'sugestao': prod_b,
                        'prob': prob_condicional
                    })

    def gerar_texto(self):
        if not self.insights: return None
        
        msg = "💡 *INSIGHT DE VENDA CASADA*\n\n"
        for i in self.insights[:3]:
            msg += f"• Quem compra *{i['base']}* tem *{i['prob']:.0%}* de chance de levar *{i['sugestao']}*.\n"
        
        msg += "\n📢 *Sugestão:* Oriente os vendedores a oferecerem esse combo!"
        return msg