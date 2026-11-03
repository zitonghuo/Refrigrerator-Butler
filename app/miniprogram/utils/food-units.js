const units = ['个', 'g', 'kg', '斤', 'mL', 'L', '颗', '根', '棵', '片', '块', '份', '把', '盒', '袋', '瓶', '包'];
function suggestedUnit(name) {
  if (/牛奶|酸奶|豆浆|果汁|酱油|食用油|醋|饮料/.test(name)) return 'mL';
  if (/鸡蛋|鸭蛋|鹅蛋|皮蛋|肉包/.test(name)) return '个';
  if (/肉|牛排|排骨|里脊|五花|牛腩|鸡胸|鸡腿|鸡翅|火腿|培根|鱼|虾|蘑菇|大米|面粉/.test(name)) return 'g';
  if (/菠菜|香菜|韭菜|小葱/.test(name)) return '把';
  if (/黄瓜|胡萝卜|玉米|大葱/.test(name)) return '根';
  return '个';
}
function prepareFood(food) {
  if (food.quantity && food.unit) return { ...food, unitChosen: true };
  return { ...food, unit: suggestedUnit(food.name), unitChosen: false };
}
module.exports = { units, suggestedUnit, prepareFood };
