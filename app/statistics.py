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
        inicio_hora_atual = agora.replace(minute=0, second=0, microsecond=0)

        # Janela de tempo
        ontem_mesmo_horario = agora - timedelta(days=1)
        inicio_hora_ontem = inicio_hora_atual - timedelta(days=1)

        # Vendas Hoje
        self.venda_hoje_hora = self.df[
            (self.df["timestamp"] >= inicio_hora_atual) &
            (self.df["timestamp"] <= agora)
        ]["valor_total"].sum()

        # Vendas ontem
        self.venda_ontem_hora = self.df[
            (self.df["timestamp"] >= inicio_hora_ontem) &
            (self.df["timestamp"] <= ontem_mesmo_horario)
        ]["valor_total"].sum()

        # Projeção
        venda_total_ontem = self.df[
            (self.df['timestamp'].dt.date == (agora - timedelta(days=1)).date())
        ]['valor_total'].sum()
        
        self.venda_total_ontem = venda_total_ontem
        
        if self.venda_ontem_hora > 0:
            self.variacao_hora = (self.venda_hoje_hora / self.venda_ontem_hora) - 1
            self.projecao_hoje = venda_total_ontem * (1 + self.variacao_hora)
        else:
            self.variacao_hora = 0
            self.projecao_hoje = self.venda_hoje_hora # Simplificação se não houve venda ontem

    def gerar_texto(self):
        agora = datetime.now()
        dia_semana_ontem = format_date((agora - timedelta(days=1)).strftime('%A'), format='EEEE', locale='pt_BR')
        hora_str = agora.strftime('%Hh')

        emoji = "📈" if self.variacao_hora >= 0 else "📉"
        sinal = "+" if self.variacao_hora >= 0 else ""

        return (
            f"{emoji} *Performance Comparativa*\n\n"
            f"• {dia_semana_ontem} {hora_str}: R$ {self.venda_ontem_hora:,.2f}\n"
            f"• Hoje {hora_str}: R$ {self.venda_hoje_hora:,.2f} ({sinal}{self.variacao_hora:.1%})\n\n"
            f"🎯 *Projeção de Fechamento:*\n"
            f"R$ {self.projecao_hoje:,.2f} vs R$ {self.venda_total_ontem:,.2f} (ontem)"
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
        
        msg = "💡 *INSIGHT DE VENDA CASADA (BAYES)*\n\n"
        for i in self.insights[:3]:
            msg += f"• Quem compra *{i['base']}* tem *{i['prob']:.0%}* de chance de levar *{i['sugestao']}*.\n"
        
        msg += "\n📢 *Sugestão:* Oriente os vendedores a oferecerem esse combo!"
        return msg