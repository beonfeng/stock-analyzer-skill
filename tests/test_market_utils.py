#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
market_utils 模块的单元测试

测试覆盖：
- 港股代码识别（00700、09988）
- A 股代码识别（600519、000001）
- 价格转换（港股 458200 → 458.2，A 股 8250 → 82.5）
- 异常值处理（None、0、'-'）
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from scripts.market_utils import get_market_info, convert_price, is_hk_stock, get_secid


class TestGetMarketInfo:
    """测试 get_market_info 函数"""

    # === 港股测试 ===

    def test_hk_stock_tencent(self):
        """测试腾讯港股代码 00700"""
        assert get_market_info('00700') == ('HK', 116, 1000)

    def test_hk_stock_alibaba(self):
        """测试阿里巴巴港股代码 09988"""
        assert get_market_info('09988') == ('HK', 116, 1000)

    def test_hk_stock_min_code(self):
        """测试港股最小代码 00001"""
        assert get_market_info('00001') == ('HK', 116, 1000)

    def test_hk_stock_max_code(self):
        """测试港股最大代码 99999"""
        assert get_market_info('99999') == ('HK', 116, 1000)

    def test_hk_stock_numeric_input_short(self):
        """测试短数字输入（700 转为 '700'，不是 5 位，应抛异常）"""
        with pytest.raises(ValueError, match="无法识别"):
            get_market_info(700)

    def test_hk_stock_numeric_input_5digit(self):
        """测试 5 位数字输入（应转为字符串后识别为港股）"""
        assert get_market_info(70000) == ('HK', 116, 1000)

    # === 上海 A 股测试 ===

    def test_sh_stock_moutai(self):
        """测试贵州茅台代码 600519"""
        assert get_market_info('600519') == ('SH', 1, 100)

    def test_sh_stock_icbc(self):
        """测试工商银行代码 601398"""
        assert get_market_info('601398') == ('SH', 1, 100)

    def test_sh_stock_startswith_6(self):
        """测试所有 6 开头的代码都是上海"""
        assert get_market_info('600000') == ('SH', 1, 100)
        assert get_market_info('688001') == ('SH', 1, 100)

    # === 深圳 A 股测试 ===

    def test_sz_stock_ping_an_bank(self):
        """测试平安银行代码 000001"""
        assert get_market_info('000001') == ('SZ', 0, 100)

    def test_sz_stock_startswith_0(self):
        """测试 0 开头的深圳代码"""
        assert get_market_info('000002') == ('SZ', 0, 100)
        assert get_market_info('002594') == ('SZ', 0, 100)

    def test_sz_stock_startswith_3(self):
        """测试 3 开头的创业板代码"""
        assert get_market_info('300750') == ('SZ', 0, 100)
        assert get_market_info('300059') == ('SZ', 0, 100)

    # === 异常输入测试 ===

    def test_invalid_code_too_short(self):
        """测试过短的代码"""
        with pytest.raises(ValueError, match="无法识别"):
            get_market_info('123')

    def test_invalid_code_too_long(self):
        """测试过长的代码（非 5 位且非 6 位）"""
        with pytest.raises(ValueError, match="无法识别"):
            get_market_info('1234567')

    def test_invalid_code_letters(self):
        """测试包含字母的代码"""
        with pytest.raises(ValueError, match="无法识别"):
            get_market_info('AAPL')

    def test_invalid_code_empty(self):
        """测试空字符串"""
        with pytest.raises(ValueError, match="无法识别"):
            get_market_info('')

    def test_4_digit_code_raises(self):
        """测试 4 位代码"""
        with pytest.raises(ValueError, match="无法识别"):
            get_market_info('1234')

    def test_code_with_whitespace(self):
        """测试带空格的代码"""
        assert get_market_info(' 00700 ') == ('HK', 116, 1000)
        assert get_market_info('  600519  ') == ('SH', 1, 100)


class TestConvertPrice:
    """测试 convert_price 函数"""

    # === 港股价格转换 ===

    def test_hk_price_normal(self):
        """测试港股正常价格转换：458200 → 458.2"""
        assert convert_price(458200, 'HK') == pytest.approx(458.2)

    def test_hk_price_tencent(self):
        """测试腾讯股价：350000 → 350.0"""
        assert convert_price(350000, 'HK') == pytest.approx(350.0)

    def test_hk_price_small(self):
        """测试港股小额价格：1000 → 1.0"""
        assert convert_price(1000, 'HK') == pytest.approx(1.0)

    def test_hk_price_string_input(self):
        """测试字符串输入"""
        assert convert_price('458200', 'HK') == pytest.approx(458.2)

    # === A 股价格转换 ===

    def test_a_share_price_normal(self):
        """测试 A 股正常价格转换：8250 → 82.5"""
        assert convert_price(8250, 'SH') == pytest.approx(82.5)
        assert convert_price(8250, 'SZ') == pytest.approx(82.5)

    def test_a_share_price_moutai(self):
        """测试茅台价格：168800 → 1688.0"""
        assert convert_price(168800, 'SH') == pytest.approx(1688.0)

    def test_a_share_price_small(self):
        """测试 A 股小额价格：100 → 1.0"""
        assert convert_price(100, 'SH') == pytest.approx(1.0)

    def test_a_share_price_string_input(self):
        """测试字符串输入"""
        assert convert_price('8250', 'SZ') == pytest.approx(82.5)

    # === 异常值处理 ===

    def test_none_returns_zero(self):
        """测试 None 输入返回 0"""
        assert convert_price(None, 'HK') == 0.0
        assert convert_price(None, 'SH') == 0.0

    def test_dash_returns_zero(self):
        """测试 '-' 输入返回 0"""
        assert convert_price('-', 'HK') == 0.0
        assert convert_price('-', 'SH') == 0.0

    def test_zero_returns_zero(self):
        """测试 0 输入返回 0"""
        assert convert_price(0, 'HK') == 0.0
        assert convert_price(0, 'SZ') == 0.0

    def test_empty_string_returns_zero(self):
        """测试空字符串输入返回 0"""
        assert convert_price('', 'HK') == 0.0

    def test_invalid_string_returns_zero(self):
        """测试无效字符串输入返回 0"""
        assert convert_price('abc', 'HK') == 0.0
        assert convert_price('N/A', 'SH') == 0.0

    def test_float_input(self):
        """测试浮点数输入"""
        assert convert_price(458200.5, 'HK') == pytest.approx(458.2005)

    def test_invalid_market_raises(self):
        """测试无效市场类型抛异常"""
        with pytest.raises(ValueError, match="无效"):
            convert_price(100, 'XX')


class TestIsHkStock:
    """测试 is_hk_stock 函数"""

    def test_hk_stock_returns_true(self):
        """测试港股代码返回 True"""
        assert is_hk_stock('00700') is True
        assert is_hk_stock('09988') is True
        assert is_hk_stock('00001') is True

    def test_a_share_returns_false(self):
        """测试 A 股代码返回 False"""
        assert is_hk_stock('600519') is False
        assert is_hk_stock('000001') is False
        assert is_hk_stock('300750') is False

    def test_invalid_code_returns_false(self):
        """测试无效代码返回 False"""
        assert is_hk_stock('AAPL') is False
        assert is_hk_stock('') is False
        assert is_hk_stock('123') is False


class TestGetSecid:
    """测试 get_secid 函数"""

    def test_hk_secid(self):
        """测试港股 secid"""
        assert get_secid('00700', 116) == '116.00700'

    def test_sh_secid(self):
        """测试上海 secid"""
        assert get_secid('600519', 1) == '1.600519'

    def test_sz_secid(self):
        """测试深圳 secid"""
        assert get_secid('000001', 0) == '0.000001'

    def test_secid_format(self):
        """测试 secid 格式正确"""
        result = get_secid('300750', 0)
        assert '.' in result
        parts = result.split('.')
        assert len(parts) == 2
        assert parts[0] == '0'
        assert parts[1] == '300750'


class TestIntegration:
    """集成测试：组合使用多个函数"""

    def test_hk_full_workflow(self):
        """测试港股完整工作流"""
        code = '00700'
        market_code, market_id, price_divisor = get_market_info(code)

        assert market_code == 'HK'
        assert market_id == 116
        assert price_divisor == 1000
        assert is_hk_stock(code) is True
        assert get_secid(code, market_id) == '116.00700'
        assert convert_price(350000, market_code) == pytest.approx(350.0)

    def test_sh_full_workflow(self):
        """测试上海 A 股完整工作流"""
        code = '600519'
        market_code, market_id, price_divisor = get_market_info(code)

        assert market_code == 'SH'
        assert market_id == 1
        assert price_divisor == 100
        assert is_hk_stock(code) is False
        assert get_secid(code, market_id) == '1.600519'
        assert convert_price(168800, market_code) == pytest.approx(1688.0)

    def test_sz_full_workflow(self):
        """测试深圳 A 股完整工作流"""
        code = '000001'
        market_code, market_id, price_divisor = get_market_info(code)

        assert market_code == 'SZ'
        assert market_id == 0
        assert price_divisor == 100
        assert is_hk_stock(code) is False
        assert get_secid(code, market_id) == '0.000001'
        assert convert_price(1250, market_code) == pytest.approx(12.5)

    def test_multiple_hk_stocks(self):
        """测试多只港股"""
        hk_codes = ['00700', '09988', '02318', '00005', '01810']
        for code in hk_codes:
            market_code, market_id, _ = get_market_info(code)
            assert market_code == 'HK', f"{code} 应该是港股"
            assert market_id == 116, f"{code} 市场 ID 应该是 116"
            assert is_hk_stock(code) is True

    def test_multiple_a_shares(self):
        """测试多只 A 股"""
        sh_codes = ['600519', '601398', '600036']
        sz_codes = ['000001', '300750', '002594']

        for code in sh_codes:
            market_code, market_id, _ = get_market_info(code)
            assert market_code == 'SH', f"{code} 应该是上海"
            assert market_id == 1

        for code in sz_codes:
            market_code, market_id, _ = get_market_info(code)
            assert market_code == 'SZ', f"{code} 应该是深圳"
            assert market_id == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
