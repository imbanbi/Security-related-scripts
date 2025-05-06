"""
该代码搜取范围过广，但应该挺齐
"""
#!/usr/bin/env python3
import re
import glob
from urllib.parse import unquote


def extract_payloads_from_file(filename):
    """
    从 XML 文件中提取可能的可疑参数、路径或口令字符串。
        提取规则包括：
      1. 原始匹配：URL（http:// 或 https:// 开头）、绝对路径（以 / 开头）、查询参数（以 ? 开头）、IPv4 地址、
         key=value 形式、Windows 路径。
      2. 补充匹配：从整个文件内容中额外提取短小单词和短语，
         - 单个单词：由字母、数字、下划线、点、减号构成，长度 1～40；
         - 两至三个单词组合：允许单词之间有空格，捕获类似 "s down"、"rsv bp" 的短组合（总长不超过 40）。
        注意：在处理前先对整个文件内容做 URL 解码（例如 %22 会被转换）。
    所有匹配结果均会先去除其中的 "https://" 前缀。
    """
    with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        # URL 解码处理
    content = unquote(content)

    results = []

    # 1. 原始匹配：采用非贪婪模式，匹配直到遇到引号、尖括号或换行符
    pattern1 = re.compile(
        r'(https?://.+?)(?=["\'<>\n])'
        r'|(/.+?)(?=["\'<>\n])'        r'|(\?.+?)(?=["\'<>\n])'        r'|(\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b)'        r'|([a-zA-Z0-9_-]+=[^"\'<>\n]+)'        r'|([a-zA-Z]:\\.+?)(?=["\'<>\n])')
    matches1 = pattern1.findall(content)
    for tup in matches1:
        # 每个元组中只有一个捕获组有内容
        for s in tup:
            if s:
                cleaned = s.replace("https://", "")
                results.append(cleaned)

                # 2. 补充匹配：提取所有单个单词（不含空格），长度 1～40
    words_no_space = re.findall(r'\b[\w\.\-]{1,40}\b', content)
    for token in words_no_space:
        token = token.replace("https://", "")
        results.append(token)

        # 3. 补充匹配：提取包含空格的短组合（2-3个单词），总长度不超过 40    words_with_space = re.findall(r'\b[\w\.\-]+(?:\s+[\w\.\-]+){1,2}\b', content)
    for token in words_with_space:
        token = token.replace("https://", "")
        if len(token) <= 40:
            results.append(token)

    return results


def process_special_token(token):
    """
    对包含 '?' 的 token 进行特殊处理：
      - 将 token 按 '?' 拆分为路径部分和查询参数部分；
      - 对路径部分：保留整个路径（不带查询参数），同时按 '/' 分割提取各个完整部分（忽略空字符串）。
      - 对查询参数部分：以 '&' 拆分后，对于每个参数以 '=' 分割，
            保留参数名；对于参数值，若其长度较短（≤20）则保留，否则舍弃。
    返回处理后的 token 列表。
    """
    if '?' not in token:
        return [token]
    new_tokens = []
    # 只拆分第一个 '?' 之前的路径和之后的查询字符串
    path, query = token.split('?', 1)
    if path:
        # 添加完整路径（不带查询参数）
        new_tokens.append(path)
        # 按 '/' 分割路径，过滤掉空字符串，添加每个完整部分
        segments = [seg for seg in path.split('/') if seg]
        new_tokens.extend(segments)
        # 处理查询参数部分：以 '&' 分割参数
    params = query.split('&')
    for param in params:
        if '=' in param:
            key, value = param.split('=', 1)
            if key:
                new_tokens.append(key)
                # 只保留较短的参数值，防止输出过长
            if value and len(value) <= 20:
                new_tokens.append(value)
        else:
            if len(param) <= 20:
                new_tokens.append(param)
    return new_tokens


def post_process_tokens(tokens):
    """
    对所有提取的 token 进行后处理：
      - 对于包含 '?' 的 token，调用 process_special_token() 进行特殊拆分；
      - 其它 token 保持不变。
    返回处理后的 token 列表。
    """
    processed = []
    for token in tokens:
        if '?' in token:
            processed.extend(process_special_token(token))
        else:
            processed.append(token)
    return processed


def is_valid_token(token):
    """  
    判断 token 是否为合法的“网站路径”部分。  
    要求：  
      - 不含中文字符；  
      - 不含任何空白字符；  
      - 如果 token 以 '/' 开头，则除 '/' 外，其余字符必须全在 allowed_chars_full 中；  
        否则 token 中的每个字符必须全在 allowed_chars_simple 中。  
    这里 allowed_chars_simple 定义为 URL 中 unreserved 字符：A-Z, a-z, 0-9, '-', '.', '_', '~'  
    allowed_chars_full 除了允许 '/' 外，其余字符要求与 allowed_chars_simple 相同。  
    """  # 不允许中文
    if re.search(r'[\u4e00-\u9fff]', token):
        return False
        # 不允许空白字符
    if re.search(r'\s', token):
        return False
    allowed_chars_simple = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
    if token.startswith("/"):
        # 对于全路径 token，允许 '/' 出现，其它字符必须在 allowed_chars_simple 中
        for c in token:
            if c != "/" and c not in allowed_chars_simple:
                return False
        return True else:
        for c in token:
            if c not in allowed_chars_simple:
                return False
        return True


def final_token_cleanup(tokens):
    """
    对 token 进行最终清理：
      - 去掉每个 token 首尾的 '/'；
      - 删除空字符串；
      - 删除过长（超过20位）的纯数字 token。
    """
    new_tokens = []
    for token in tokens:
        # 去掉首尾的 '/'        token = token.strip('/')
        if not token:
            continue
            # 如果 token 全为数字且长度超过20，则跳过
        if token.isdigit() and len(token) > 20:
            continue
        new_tokens.append(token)
    return new_tokens


def main():
    payloads = set()
    # 遍历当前目录下所有 .xml 文件
    xml_files = glob.glob("*.xml")
    for xml_file in xml_files:
        payloads.update(extract_payloads_from_file(xml_file))
        # 对所有 token 进行特殊后处理
    all_tokens = post_process_tokens(list(payloads))
    # 过滤掉长度超过65的字符串
    filtered_tokens = [t for t in all_tokens if len(t) <= 65]
    # 过滤掉包含中文或含有不可能出现在网站路径中的字符的 token    valid_tokens = [t for t in filtered_tokens if is_valid_token(t)]
    # 最终清理：去除首尾的 '/' 和删除过长的纯数字 token（超过20位）
    cleaned_tokens = final_token_cleanup(valid_tokens)
    # 去重后按字符串长度（由短到长），相同长度时按字典序排序
    sorted_tokens = sorted(set(cleaned_tokens), key=lambda x: (len(x), x))
    # 将排序结果写入 output.txt，每行一个 token    with open("output.txt", "w", encoding="utf-8") as f:
    for token in sorted_tokens:
        f.write(token + "\n")


if __name__ == '__main__':
    main()