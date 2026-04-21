def detect_format(blob: bytes) -> str:
    """
    Devuelve 'ttt' o 'bt3' según la firma del archivo.
    pMdl / pMdF (M mayúscula) → TTT
    pmdl (todo minúscula)     → BT3
    """
    if len(blob) < 4:
        return 'ttt'
    magic = blob[0:4]
    if magic in (b'pMdl', b'pMdF'):
        return 'ttt'
    if magic == b'pmdl':
        return 'bt3'
    return 'bt3' if blob[1] == 0x6D else 'ttt'
