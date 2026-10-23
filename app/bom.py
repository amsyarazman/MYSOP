"""Owner-only working bills of materials, independent of published SOPs."""
import json
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CostModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class MaterialPrice(CostModel):
    name: str = Field(min_length=1, max_length=160)
    unit: str = Field(min_length=1, max_length=40)
    pack_quantity: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=4, allow_inf_nan=False)
    pack_cost: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=4, allow_inf_nan=False)

    @model_validator(mode='after')
    def paired_price(self):
        if (self.pack_quantity is None) != (self.pack_cost is None):
            raise ValueError('Supply both pack size and pack price, or leave both blank')
        return self


class OtherCost(CostModel):
    name: str = Field(min_length=1, max_length=160)
    per_serving: Decimal = Field(ge=0, max_digits=14, decimal_places=4, allow_inf_nan=False)


class BillInput(CostModel):
    currency: Literal['MYR', 'SGD', 'USD', 'EUR', 'GBP'] = 'MYR'
    prices: list[MaterialPrice] = Field(default_factory=list, max_length=100)
    other_costs: list[OtherCost] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def unique_materials(self):
        keys = [(p.name, p.unit) for p in self.prices]
        if len(keys) != len(set(keys)):
            raise ValueError('Enter one pack price per material and unit')
        return self


def sop_content(content):
    """Explicit public fields: procurement data never leaves a normal SOP route."""
    result = {k: v for k, v in content.items() if k in {
        'title', 'category', 'description', 'servings', 'steps', 'allergens',
        'safety_notes', 'photo_data_url',
    }}
    result['ingredients'] = [
        {k: v for k, v in i.items() if k in {'name', 'quantity', 'unit', 'measure_note'}}
        for i in content['ingredients']
    ]
    return result


def seed_legacy_bill(db, sop_id, content):
    prices = {}
    for i in content['ingredients']:
        if i.get('pack_cost') is not None and i.get('pack_quantity') is not None:
            prices[(i['name'], i['unit'])] = {
                k: i[k] for k in ('name', 'unit', 'pack_quantity', 'pack_cost')
            }
    if prices:
        bill = {'currency': content.get('currency', 'MYR'), 'prices': list(prices.values()), 'other_costs': []}
        db.execute('INSERT OR IGNORE INTO bills_of_materials VALUES(?,?,1)', (sop_id, json.dumps(bill)))
