"""雷速体育数据解密模块

两种解密链路:
1. web-gateway API: roott(data, code-100) → base64 → gzip(wbits=31) → URL decode → JSON
2. Canvas页面:     roott(data, 13)       → base64 → zlib(wbits=15) → URL decode → JSON

关键: roott是减shift(解密方向), 不是加shift!
"""
import base64
import zlib
import json
import urllib.parse


def roott(s: str, shift: int) -> str:
    """Caesar位移 - 解密方向(减shift)
    
    JS源码: x = (code - base - shift + 26) % 26 + base
    注意: 这里的shift在解密时是减, 加密时才是加
    """
    result = []
    for c in s:
        v = ord(c)
        if 65 <= v <= 90:    # A-Z
            x = (v - 65 - shift + 26) % 26 + 65
        elif 97 <= v <= 122:  # a-z
            x = (v - 97 - shift + 26) % 26 + 97
        else:
            x = v
        result.append(chr(x))
    return ''.join(result)


def decrypt_web_gateway(encrypted_data: str, code: int):
    """解密web-gateway API响应
    
    Args:
        encrypted_data: 响应中的data字段
        code: 响应中的code字段(100-126动态变化)
    
    Returns:
        解密后的Python对象
    """
    if code == 0:
        return encrypted_data  # 已经是明文
    if code < 100 or code > 126:
        raise ValueError(f"Unsupported code: {code}")
    
    shift = code - 100
    shifted = roott(encrypted_data, shift)
    raw = base64.b64decode(shifted)
    data = zlib.decompress(raw, 31)  # gzip (wbits=31)
    text = data.decode('utf-8', errors='replace')
    text = urllib.parse.unquote(text)
    return json.loads(text)


def decrypt_canvas(encrypted_data: str):
    """解密Canvas页面加密文本
    
    Canvas固定shift=13, 压缩用zlib(wbits=15)
    用于从页面HTML中提取比赛列表数据
    
    Args:
        encrypted_data: Canvas加密文本
    
    Returns:
        解密后的Python对象(通常是比赛列表)
    """
    shifted = roott(encrypted_data, 13)
    raw = base64.b64decode(shifted)
    data = zlib.decompress(raw, 15)  # zlib (wbits=15)
    text = data.decode('utf-8', errors='replace')
    text = urllib.parse.unquote(text)
    return json.loads(text)


def decrypt_auto(data: str, code: int):
    """自动选择解密方式
    
    code=0: 明文
    code 100-126: web-gateway加密
    其他: 尝试Canvas解密
    """
    if code == 0:
        return data
    elif 100 <= code <= 126:
        return decrypt_web_gateway(data, code)
    else:
        raise ValueError(f"Unknown code: {code}, cannot auto-decrypt")
