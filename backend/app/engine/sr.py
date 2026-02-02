class SREngine:
    @staticmethod
    def classify_levels(zones: list, cmp: float):
        """
        Classifies zones as Support (below CMP) or Resistance (above CMP).
        """
        supports = [z for z in zones if z['price'] < cmp]
        resistances = [z for z in zones if z['price'] > cmp]
        
        # Sort supports from high to low (nearest first)
        supports = sorted(supports, key=lambda x: x['price'], reverse=True)
        # Sort resistances from low to high (nearest first)
        resistances = sorted(resistances, key=lambda x: x['price'])
        
        return supports[:4], resistances[:4]
