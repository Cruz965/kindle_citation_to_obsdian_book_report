import os
import re
import sys
from bs4 import BeautifulSoup

def pausar_e_sair():
    input("\nPressione ENTER para fechar a janela...")
    sys.exit()

# =====================================================================
# BLOCO 1: CAMINHOS E FILTROS
# =====================================================================

# ATENÇÃO: Substitua os caminhos abaixo pelos diretórios do seu computador
ARQUIVO_HTML_KINDLE = "C:/Caminho/Para/Exportacao_Kindle.html"
ARQUIVO_OBSIDIAN = "C:/Caminho/Para/Seu/Obsidian/Bibliografia/Fichamento_Novo.md"

PAGINA_INICIAL = None
PAGINA_FINAL = None

# =====================================================================
# BLOCO 2: LEITURA E VALIDAÇÃO DO ARQUIVO OBSIDIAN
# =====================================================================

if not os.path.exists(ARQUIVO_OBSIDIAN):
    print(f"ERRO: O arquivo {ARQUIVO_OBSIDIAN} não foi encontrado.")
    pausar_e_sair()

with open(ARQUIVO_OBSIDIAN, 'r', encoding='utf-8') as f:
    conteudo_md = f.read()

def extrair_propriedade(prop, texto):
    match = re.search(rf'^{prop}:\s*(.+)$', texto, re.MULTILINE | re.IGNORECASE)
    if match:
        valor = match.group(1).strip().strip('"\'')
        if valor.lower() != 'sem valor' and valor != '':
            return valor
    return None

titulo_fm = extrair_propriedade("titulo", conteudo_md)
ano_fm = extrair_propriedade("ano", conteudo_md)
editora_fm = extrair_propriedade("editora", conteudo_md)
autor_fm = extrair_propriedade("autor", conteudo_md)
cidade_fm = extrair_propriedade("cidade", conteudo_md) or ""

if not ano_fm:
    ano_fm = "s.d."
if not editora_fm:
    editora_fm = "Desconhecida"

partes_bibtex = re.split(r'^#*\s*Bibtex:?\s*$', conteudo_md, maxsplit=1, flags=re.MULTILINE|re.IGNORECASE)
if len(partes_bibtex) < 2:
    print("ERRO: A seção 'Bibtex' não foi encontrada no seu template.")
    pausar_e_sair()
topo_e_bibtex, resto = partes_bibtex

partes_notas = re.split(r'^#*\s*Notas literárias:?\s*$', resto, maxsplit=1, flags=re.MULTILINE|re.IGNORECASE)
if len(partes_notas) < 2:
    print("ERRO: A seção 'Notas literárias' não foi encontrada no seu template.")
    pausar_e_sair()
meio_bruto, raw_notas = partes_notas

partes_meio = meio_bruto.split('---', 1)
if len(partes_meio) > 1:
    meio_preservado = "\n\n---\n" + partes_meio[1].strip() + "\n\n"
else:
    meio_preservado = "\n\n" + meio_bruto.strip() + "\n\n"

# =====================================================================
# BLOCO 3: PROCESSAMENTO DO KINDLE E CITEKEY
# =====================================================================

try:
    with open(ARQUIVO_HTML_KINDLE, 'r', encoding='utf-8') as file:
        soup = BeautifulSoup(file, 'html.parser')
except FileNotFoundError:
    print(f"ERRO: O HTML do Kindle ({ARQUIVO_HTML_KINDLE}) não foi encontrado.")
    pausar_e_sair()

try:
    title_html = soup.find('div', class_='bookTitle').text.strip()
    title_html = re.sub(r'\s*\(.*?\)', '', title_html).strip()
    author_html = soup.find('div', class_='authors').text.strip()
except AttributeError:
    title_html = "Livro_Desconhecido"
    author_html = "Autor_Desconhecido"

titulo_final = titulo_fm if titulo_fm else title_html
autor_final = autor_fm if autor_fm else author_html
last_name = autor_final.split()[-1].lower() if autor_final else "autor"
cite_key = f"{last_name}{ano_fm}"

# =====================================================================
# BLOCO 4: LEITURA SEQUENCIAL COM EXTRAÇÃO DE CAPÍTULOS
# =====================================================================

# Adicionamos 'sectionHeading' na busca para rastrear os capítulos
elements = soup.find_all('div', class_=['sectionHeading', 'noteHeading', 'noteText'])
parsed_items = []
current_heading = None
current_chapter = None

for el in elements:
    classes = el.get('class', [])
    if 'sectionHeading' in classes:
        current_chapter = el.text.strip().replace('\xa0', ' ')
    elif 'noteHeading' in classes:
        current_heading = el.text.strip().replace('\xa0', ' ')
    elif 'noteText' in classes:
        if current_heading:
            parsed_items.append({
                'chapter': current_chapter,
                'heading': current_heading,
                'text': el.text.strip()
            })
            current_heading = None

entradas_agrupadas = []
entrada_atual = None

for item in parsed_items:
    head_text = item['heading']
    content = item['text']
    capitulo = item['chapter']
    
    page_match = re.search(r'(?i)(página|page)\s*(\d+)', head_text)
    loc_match = re.search(r'(?i)(posição|location)\s*(\d+)', head_text)
    
    pagina_atual = int(page_match.group(2)) if page_match else (int(loc_match.group(2)) if loc_match else 0)
    location_info = f"p. {pagina_atual}" if page_match else (f"pos. {pagina_atual}" if loc_match else "")
    
    texto_cabecalho = head_text.lower()
    is_nota = "nota" in texto_cabecalho or "note" in texto_cabecalho or "anotação" in texto_cabecalho
    if "destaque" in texto_cabecalho or "highlight" in texto_cabecalho or "marcação" in texto_cabecalho:
        is_nota = False
        
    if is_nota:
        if entrada_atual and entrada_atual['pagina'] == pagina_atual:
            if entrada_atual['anotacao']:
                entrada_atual['anotacao'] += f"\n\n{content}"
            else:
                entrada_atual['anotacao'] = content
        else:
            if entrada_atual:
                entradas_agrupadas.append(entrada_atual)
            entrada_atual = {'pagina': pagina_atual, 'location_info': location_info, 'grifo': '', 'anotacao': content, 'capitulo': capitulo}
    else:
        if entrada_atual:
            entradas_agrupadas.append(entrada_atual)
        entrada_atual = {'pagina': pagina_atual, 'location_info': location_info, 'grifo': content, 'anotacao': '', 'capitulo': capitulo}

if entrada_atual:
    entradas_agrupadas.append(entrada_atual)

# =====================================================================
# BLOCO 5: CRUZAMENTO DE DADOS (NOVAS VS ANTIGAS E INJEÇÃO DE CAPÍTULO)
# =====================================================================

notas_antigas = []
blocos_existentes = re.split(r'\n---\n', raw_notas)

for bloco in blocos_existentes:
    # Limpa capítulos antigos (se existirem) para não duplicá-los ao reconstruir
    bloco = re.sub(r'^###\s+[^\n]+\n*', '', bloco).strip()
    if not bloco: continue
    
    match = re.search(r'\\cite\[(?:p\.\vert{}pos\.)\s*(\d+)\]', bloco)
    sort_val = int(match.group(1)) if match else 999999
    
    # Cruza com as entradas do Kindle para resgatar a qual capítulo esta nota antiga pertence
    cap_found = None
    for ent in entradas_agrupadas:
        if (ent['grifo'] and ent['grifo'][:50] in bloco) or (ent['anotacao'] and ent['anotacao'][:50] in bloco):
            cap_found = ent['capitulo']
            break
            
    notas_antigas.append({'sort_val': sort_val, 'texto': bloco, 'capitulo': cap_found})

notas_novas = []

for entrada in entradas_agrupadas:
    if PAGINA_INICIAL is not None and entrada['pagina'] < PAGINA_INICIAL: continue
    if PAGINA_FINAL is not None and entrada['pagina'] > PAGINA_FINAL: continue
    
    md_nota = ""
    if entrada['grifo']:
        md_nota += f"**Grifo ({entrada['location_info']}):** {entrada['grifo']}\n\n"
    
    if entrada['anotacao']:
        md_nota += f"**Sua anotação:** {entrada['anotacao']}\n\n"
        
    latex_cite = f"\\cite[{entrada['location_info']}]{{{cite_key}}}" if entrada['location_info'] else f"\\cite{{{cite_key}}}"
    md_nota += f"`{latex_cite}`"
    
    duplicada = False
    if entrada['grifo']:
        duplicada = any(entrada['grifo'][:50] in n['texto'] for n in notas_antigas)
    elif entrada['anotacao']:
        duplicada = any(entrada['anotacao'][:50] in n['texto'] for n in notas_antigas)
        
    if not duplicada:
        if not any(md_nota[:100] in n['texto'] for n in notas_novas):
            notas_novas.append({'sort_val': entrada['pagina'] if entrada['pagina'] > 0 else 999999, 'texto': md_nota})

# Ordenação
notas_antigas.sort(key=lambda x: x['sort_val'])
notas_novas.sort(key=lambda x: x['sort_val'])

# Constrói o texto das notas antigas já embutindo o título do capítulo
textos_antigas = []
current_cap = None
for n in notas_antigas:
    if n.get('capitulo') and n['capitulo'] != current_cap:
        current_cap = n['capitulo']
        textos_antigas.append(f"### {current_cap}\n\n{n['texto']}")
    else:
        textos_antigas.append(n['texto'])

# =====================================================================
# BLOCO 6: RECONSTRUÇÃO DO ARQUIVO FINAL
# =====================================================================

crases = "```"
bibtex_block = f"""
{crases}bibtex
@book{{{cite_key},
  author = {{{autor_final}}},
  title = {{{titulo_final}}},
  year = {{{ano_fm}}},
  publisher = {{{editora_fm}}},
  address = {{{cidade_fm}}}
}}
{crases}
"""

novo_conteudo = topo_e_bibtex.strip() + "\n\n"
novo_conteudo += "## Bibtex:\n\n" + bibtex_block.strip() + "\n"
novo_conteudo += meio_preservado
novo_conteudo += "## Notas literárias:\n\n"

# Junta primeiro as novas, depois as antigas processadas com capítulos
todas_as_notas = [n['texto'] for n in notas_novas] + textos_antigas

novo_conteudo += "\n\n---\n\n".join(todas_as_notas)
novo_conteudo += "\n\n---\n"

with open(ARQUIVO_OBSIDIAN, 'w', encoding='utf-8') as f:
    f.write(novo_conteudo)

print(f"SUCESSO! Foram adicionadas {len(notas_novas)} notas novas no topo e as antigas foram separadas por capítulo.")
pausar_e_sair()