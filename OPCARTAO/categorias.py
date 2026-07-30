"""Legenda de categorias de consumo (padrão Sicredi)."""

LEGENDA_CATEGORIAS = [
    {'slug': 'artigos', 'nome': 'Artigos', 'icone': 'fa-shopping-basket'},
    {'slug': 'roupas', 'nome': 'Roupas', 'icone': 'fa-tshirt'},
    {'slug': 'educacao', 'nome': 'Educação', 'icone': 'fa-graduation-cap'},
    {'slug': 'entretenimento', 'nome': 'Entretenimento', 'icone': 'fa-play-circle'},
    {'slug': 'saude', 'nome': 'Saúde', 'icone': 'fa-plus-square'},
    {'slug': 'casa', 'nome': 'Casa', 'icone': 'fa-home'},
    {'slug': 'mercado', 'nome': 'Mercado', 'icone': 'fa-shopping-cart'},
    {'slug': 'pet', 'nome': 'Pet', 'icone': 'fa-paw'},
    {'slug': 'restaurante', 'nome': 'Restaurante', 'icone': 'fa-utensils'},
    {'slug': 'servicos', 'nome': 'Serviços', 'icone': 'fa-envelope'},
    {'slug': 'transporte', 'nome': 'Transporte', 'icone': 'fa-car'},
    {'slug': 'viagem', 'nome': 'Viagem', 'icone': 'fa-plane'},
    {'slug': 'outros', 'nome': 'Outros', 'icone': 'fa-tag'},
]

LEGENDA_POR_SLUG = {c['slug']: c for c in LEGENDA_CATEGORIAS}

NOTA_TRANSACOES_EXTERIOR = (
    'Transações no exterior: as despesas feitas no exterior são convertidas em dólar, '
    'independente da moeda. A cotação utilizada está disponível no site do emissor. '
    'Lembre-se que há incidência de IOF em compras internacionais.'
)

MAPEAMENTO_SICOOB_LEGENDA = {
    'VESTUARIO': 'roupas',
    'SAUDE': 'saude',
    'ESPORTES LAZER E TURISMO': 'entretenimento',
    'AUTOMOVEIS, VEICULOS E TRANSPO': 'transporte',
    'POSTOS DE GASOLINA': 'transporte',
    'ALIMENTACAO': 'mercado',
    'GASTRONOMIA': 'restaurante',
    'ARTIGOS E SERVICOS PARA O LAR': 'casa',
    'ESTETICA E CUIDADOS PESSOAIS': 'saude',
    'PRESENTES, MKT DIRETO, CATALO': 'artigos',
    'DIVERSOS': 'outros',
}


def _normalizar_chave(txt: str) -> str:
    import unicodedata
    d = unicodedata.normalize('NFKD', txt or '')
    s = ''.join(c for c in d if unicodedata.category(c) != 'Mn').upper()
    return s.strip()


def slug_legenda_de_tipo(tipo_estabelecimento: str) -> str:
    chave = _normalizar_chave(tipo_estabelecimento)
    if chave in MAPEAMENTO_SICOOB_LEGENDA:
        return MAPEAMENTO_SICOOB_LEGENDA[chave]
    for padrao, slug in MAPEAMENTO_SICOOB_LEGENDA.items():
        if padrao in chave or chave in padrao:
            return slug
    return 'outros'


def enriquecer_perfil_consumo(perfil: list[dict]) -> list[dict]:
    resultado = []
    for item in perfil:
        slug = item.get('slug_legenda') or slug_legenda_de_tipo(item.get('tipo', ''))
        legenda = LEGENDA_POR_SLUG.get(slug, LEGENDA_POR_SLUG['outros'])
        resultado.append({**item, 'slug_legenda': slug, **legenda})
    return resultado


# Ícones gráficos da fatura Sicredi (hash MD5 parcial do stream da imagem).
SICREDI_ICONE_HASH_CATEGORIA = {
    'ea21cd68f482': 'transporte',
    '241eb72a1659': 'casa',
    '4bea42ed3fe5': 'servicos',
    '1552ee535831': 'servicos',
    '3c2d8f9c6376': 'restaurante',
    'a33d8267ed83': 'artigos',
    'd33daa189e60': 'saude',
    'c1621347d087': 'viagem',
}

_REGRAS_CATEGORIA = [
    ('transporte', (
        'uber', '99app', '99 ', 'cabify', 'taxi', 'localiza', 'movida', 'unidas',
        'auto posto', 'gasolina', 'shell', 'ipiranga', 'br distribuidora',
        'estacion', 'sem parar', 'veloe', 'conectcar',
    )),
    ('viagem', (
        'airbnb', 'booking', 'hotel', 'hoteis', 'latam', 'gol linhas', 'azul linhas',
        'decolar', 'cvc ', 'viagem ',
    )),
    ('servicos', (
        'google one', 'google storage', 'microsoft', 'apple.com', 'icloud', 'amazon prime',
        'aws ', 'azure', 'hostinger', 'godaddy', 'spotify', 'netflix', 'deezer',
        'wehelp', 'software', 'grafic', 'enel', 'cemig', 'copel', 'sabesp', 'claro',
        'vivo ', 'tim ', 'oi ', 'net combo', 'internet', 'telefon',
    )),
    ('entretenimento', (
        'cinema', 'ingresso', 'steam', 'playstation', 'xbox', 'nintendo', 'facbk',
        'facebook', 'disney', 'hbo', 'paramount',
    )),
    ('saude', (
        'farmacia', 'pague menos', 'drogasil', 'droga raia', 'panvel', 'clinica',
        'hospital', 'laboratorio', 'imuno', 'odont', 'medico', 'suprimedico',
        'fisio', 'fitness', 'academia', 'smart fit',
    )),
    ('mercado', (
        'carrefour', 'pao de acucar', 'extra hiper', 'assai', 'atacadao', 'supermerc',
        'mercado livre mercad', 'hortifruti', 'mercadinho',
    )),
    ('restaurante', (
        'ifood', 'restaurante', 'lanchonete', 'pizzaria', 'burger', 'mcdonald',
        'subway', 'starbucks', 'cafe ', 'padaria', 'bolo', 'gastronomia', 'bar ',
        'felicia', 'fabrica de bolos',
    )),
    ('roupas', (
        'inditex', 'zara', 'renner', 'riachuelo', 'c&a', 'hering', 'crocs',
        'vestuario', 'moda', 'calcados', 'arezzo', 'centauro',
    )),
    ('casa', (
        'leroy', 'telhanorte', 'casas bahia', 'magazine luiza', 'magalu', 'construc',
        'material de construc', 'moveis', 'colchao', 'parafuzeta', 'refricom',
        'quimica', 'esportiva', 'loja do posto', 'imperiodaconstruc',
    )),
    ('pet', ('petz', 'pet shop', 'cobasi', 'petlove')),
    ('educacao', ('udemy', 'coursera', 'alura', 'escola', 'faculdade', 'universidade')),
    ('artigos', ('mercadolivre', 'amazon', 'shopee', 'shein', 'aliexpress', 'presente')),
]


def inferir_categoria(descricao: str, tipo_compra: str = '') -> str:
    texto = _normalizar_chave(f'{descricao} {tipo_compra}')
    if not texto:
        return 'outros'
    for slug, palavras in _REGRAS_CATEGORIA:
        for palavra in palavras:
            if _normalizar_chave(palavra) in texto:
                return slug
    return 'outros'


def categoria_de_icone_sicredi(icone_hash: str) -> str:
    if not icone_hash:
        return ''
    return SICREDI_ICONE_HASH_CATEGORIA.get(icone_hash, '')


def resolver_categoria(
    descricao: str,
    *,
    tipo_compra: str = '',
    icone_hash: str = '',
) -> str:
    cat_palavra = inferir_categoria(descricao, tipo_compra)
    cat_icone = categoria_de_icone_sicredi(icone_hash)
    if cat_icone and cat_palavra == 'outros':
        return cat_icone
    if cat_palavra != 'outros':
        return cat_palavra
    return cat_icone or cat_palavra


def categoria_efetiva(descricao: str, categoria: str = '', tipo_compra: str = '') -> str:
    """Preenche categoria vazia com inferência por descrição (faturas já importadas)."""
    if categoria and categoria in LEGENDA_POR_SLUG:
        return categoria
    return inferir_categoria(descricao, tipo_compra)
