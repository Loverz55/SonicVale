# app/core/llm_engine.py
import json
# app/core/llm_engine.py

import re
import time
import random
from openai import OpenAI
from numba.cuda import stream

from app.core.prompts import get_auto_fix_json_prompt


class LLMEngine:
    def __init__(self, api_key: str, base_url: str, model_name: str, custom_params: str):
        """
        api_key: LLM API Key
        base_url: OpenAI-compatible API URL（例如企业版/自建 LLM）
        model_name: 模型名称
        custom_params: 自定义参数（JSON字符串）
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")  # 去掉末尾斜杠
        self.model_name = model_name
        
        # custom_params从string转为dict
        custom_params = json.loads(custom_params)
        if not isinstance(custom_params, dict):
            raise ValueError("无效的 custom_params")
        self.custom_params = custom_params
        
        # 使用新版 OpenAI 客户端
        self.client = OpenAI(
            api_key=api_key,
            base_url=self.base_url
        )

    def _extract_result_tag(self, text: str) -> str:
        """提取 <result> 标签内容"""
        match = re.search(r"<result>(.*?)</result>", text, re.DOTALL)
        if not match:
            raise ValueError("Response does not contain <result>...</result> tag")
        return match.group(1).strip()

    def generate_text_test(self, prompt: str) -> str:
        """
        测试：生成结果并返回（非流式）
        """
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            timeout=3000,
            **self.custom_params
        )
        return response.choices[0].message.content
    def generate_text(self, prompt: str, retries: int = 3, delay: float = 1.0) -> str:
        """
        流式生成：边生成边输出
        """
        for attempt in range(retries):
            try:
                # 开启流式
                stream = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    stream=True,
                    timeout=3000,
                    **self.custom_params
                )
                
                # 拼接 delta.content
                full_text = ""
                for chunk in stream:
                    if chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        content = delta.content if hasattr(delta, 'content') else None
                        if content:
                            print(content, end="", flush=True)  # 实时输出
                            full_text += content

                print()  # 换行
                return full_text

            except Exception as e:
                if attempt < retries - 1:
                    sleep_time = delay * (2 ** attempt) + random.random()
                    time.sleep(sleep_time)
                else:
                    raise e
    def save_load_json(self, json_str: str):
        """解析JSON，支持自动提取<result>标签内容。

        兼容两种输出：
        1) 直接输出 JSON（数组/对象）
        2) 用 <result>...</result> 包裹 JSON

        另外：如果 <result> 内是空对象 {} / 空数组 []，会尝试从原始文本中再抓取一次数组。
        """
        raw_text = json_str

        # 先尝试提取 <result> 标签内容
        try:
            json_str = self._extract_result_tag(json_str)
        except ValueError:
            # 没有 <result> 标签，直接使用原文本
            pass

        def _loads(s: str):
            return json.loads(s)

        # 尝试加载 json
        try:
            parsed = _loads(json_str)

            # 若提取到的 result 是空对象/空数组，但原文里可能还有真正的数组，则再尝试抓取一次
            if (parsed == {} or parsed == []) and raw_text and raw_text != json_str:
                # 从原始文本中抓第一个 JSON 数组（最常见）
                m = re.search(r"\[[\s\S]*\]", raw_text)
                if m:
                    try:
                        return _loads(m.group(0))
                    except Exception:
                        pass

            return parsed

        except json.JSONDecodeError:
            # JSON解析失败，尝试让LLM修复
            prompt = get_auto_fix_json_prompt(json_str)
            res = self.generate_text(prompt)
            # 递归调用，修复后的结果也可能包含 <result> 标签
            return self.save_load_json(res)

    def generate_smart_text(self, prompt: str) -> str:
        """
        智能文本生成（流式）
        """
        stream = self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            timeout=3000
        )

        # 拼接 delta.content
        full_text = ""
        for chunk in stream:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                content = delta.content if hasattr(delta, 'content') else None
                if content:
                    print(content, end="", flush=True)
                    full_text += content

        print()  # 换行
        return full_text
