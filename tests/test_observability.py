from src.observability import OpLog


def test_oplog_keeps_newest_first_and_respects_limit():
    log = OpLog(limite=3)
    for i in range(4):
        log.registrar("Redis", "SET", f"op{i}")
    recentes = log.recentes()
    assert len(recentes) == 3
    assert recentes[0].detalhe == "op3"
    assert recentes[-1].detalhe == "op1"
    assert recentes[0].banco == "Redis" and recentes[0].operacao == "SET"


def test_oplog_limpar_esvazia():
    log = OpLog()
    log.registrar("MongoDB", "insert_one", "pedidos")
    log.limpar()
    assert log.recentes() == []


def test_oplog_total_continua_contando_depois_do_limite():
    log = OpLog(limite=3)
    for i in range(5):
        log.registrar("Redis", "SET", f"op{i}")
    assert log.total == 5            # contador monotônico, independente do deque cheio
    assert len(log.recentes()) == 3  # a janela continua limitada
    log.limpar()
    assert log.total == 0
