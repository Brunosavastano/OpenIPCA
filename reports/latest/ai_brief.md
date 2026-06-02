# Brief de IA — IPCA 2026-04

_AI Replay Mode · provider: openai_

O quadro do IPCA é adverso: a inflação cheia veio pressionada, a difusão está em patamar historicamente elevado e os núcleos seguem sinalizando persistência. A composição mostra impulso relevante de alimentação, saúde e habitação, com pouco alívio vindo dos grupos de menor contribuição. Em conjunto, as evidências sustentam a classificação de pressão disseminada e um ambiente menos benigno para a dinâmica inflacionária.

## Afirmações (cada uma aterrada em evidência)
- O IPCA de abril mostrou leitura cheia pressionada, com alta de 0,67% no mês, variação em 12 meses de 4,39%, média móvel de 0,75% e leitura mensal no percentil 83,93, o que aponta para um resultado elevado tanto no nível corrente quanto na comparação histórica da série mensal.  
  _evidência: ev_headline_mom, ev_headline_12m, ev_headline_mm3, ev_headline_percentile_
- A difusão reforçou a leitura de pressão disseminada: 65,25% dos subitens subiram no mês, a média móvel ficou em 64,63% e seu percentil alcançou 94,23, indicando que a alta de preços não ficou concentrada em poucos componentes.  
  _evidência: ev_diffusion_mom, ev_diffusion_mm3, ev_diffusion_mm3_percentile_
- Os núcleos também preservaram sinal desfavorável, com média de 0,49% no mês e 0,52% na média móvel, enquanto os alertas de núcleo em base anualizada marcaram 6,37 em condição high e 7,31 em condição critical.  
  _evidência: ev_core_mean_mom, ev_core_mean_mm3, ev_alert_0, ev_alert_1_
- Na composição, Alimentação e bebidas contribuiu com 0,29 p.p., Saúde e cuidados pessoais com 0,16 p.p. e Habitação com 0,10 p.p., enquanto Educação ficou em 0,00 p.p., Transportes em 0,01 p.p. e Artigos de residência em 0,02 p.p., sugerindo que os principais vetores altistas tiveram pouco contraponto dos grupos de menor pressão.  
  _evidência: ev_contrib_top_pos_0, ev_contrib_top_pos_1, ev_contrib_top_pos_2, ev_contrib_top_neg_0, ev_contrib_top_neg_1, ev_contrib_top_neg_2_
- Os alertas de difusão aparecem simultaneamente como high e critical no nível de 94,23, e o alerta de serviços em aceleração marcou 2,88, reforçando a leitura de persistência e amplitude do processo inflacionário.  
  _evidência: ev_alert_2, ev_alert_3, ev_alert_4_
- O regime inflacionário foi classificado como Pressão disseminada.  
  _evidência: ev_regime_
