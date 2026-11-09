/*
 * Periodic table data and molar-mass parsing (pure, no DOM).
 * Masses are conventional standard atomic weights; radioactive elements carry
 * the mass number of their longest-lived isotope.
 */
(function (root, factory) {
    "use strict";

    if (typeof module === "object" && module.exports) module.exports = factory();
    else root.BiobankElnElements = factory();
})(typeof self !== "undefined" ? self : this, function () {
    "use strict";

    const RAW = "H Hydrogen 1.008|He Helium 4.0026|Li Lithium 6.94|Be Beryllium 9.0122|B Boron 10.81|C Carbon 12.011|N Nitrogen 14.007|O Oxygen 15.999|F Fluorine 18.998|Ne Neon 20.180|" +
        "Na Sodium 22.990|Mg Magnesium 24.305|Al Aluminium 26.982|Si Silicon 28.085|P Phosphorus 30.974|S Sulfur 32.06|Cl Chlorine 35.45|Ar Argon 39.948|K Potassium 39.098|Ca Calcium 40.078|" +
        "Sc Scandium 44.956|Ti Titanium 47.867|V Vanadium 50.942|Cr Chromium 51.996|Mn Manganese 54.938|Fe Iron 55.845|Co Cobalt 58.933|Ni Nickel 58.693|Cu Copper 63.546|Zn Zinc 65.38|" +
        "Ga Gallium 69.723|Ge Germanium 72.630|As Arsenic 74.922|Se Selenium 78.971|Br Bromine 79.904|Kr Krypton 83.798|Rb Rubidium 85.468|Sr Strontium 87.62|Y Yttrium 88.906|Zr Zirconium 91.224|" +
        "Nb Niobium 92.906|Mo Molybdenum 95.95|Tc Technetium 98|Ru Ruthenium 101.07|Rh Rhodium 102.91|Pd Palladium 106.42|Ag Silver 107.87|Cd Cadmium 112.41|In Indium 114.82|Sn Tin 118.71|" +
        "Sb Antimony 121.76|Te Tellurium 127.60|I Iodine 126.90|Xe Xenon 131.29|Cs Caesium 132.91|Ba Barium 137.33|La Lanthanum 138.91|Ce Cerium 140.12|Pr Praseodymium 140.91|Nd Neodymium 144.24|" +
        "Pm Promethium 145|Sm Samarium 150.36|Eu Europium 151.96|Gd Gadolinium 157.25|Tb Terbium 158.93|Dy Dysprosium 162.50|Ho Holmium 164.93|Er Erbium 167.26|Tm Thulium 168.93|Yb Ytterbium 173.05|" +
        "Lu Lutetium 174.97|Hf Hafnium 178.49|Ta Tantalum 180.95|W Tungsten 183.84|Re Rhenium 186.21|Os Osmium 190.23|Ir Iridium 192.22|Pt Platinum 195.08|Au Gold 196.97|Hg Mercury 200.59|" +
        "Tl Thallium 204.38|Pb Lead 207.2|Bi Bismuth 208.98|Po Polonium 209|At Astatine 210|Rn Radon 222|Fr Francium 223|Ra Radium 226|Ac Actinium 227|Th Thorium 232.04|" +
        "Pa Protactinium 231.04|U Uranium 238.03|Np Neptunium 237|Pu Plutonium 244|Am Americium 243|Cm Curium 247|Bk Berkelium 247|Cf Californium 251|Es Einsteinium 252|Fm Fermium 257|" +
        "Md Mendelevium 258|No Nobelium 259|Lr Lawrencium 266|Rf Rutherfordium 267|Db Dubnium 268|Sg Seaborgium 269|Bh Bohrium 270|Hs Hassium 277|Mt Meitnerium 278|Ds Darmstadtium 281|" +
        "Rg Roentgenium 282|Cn Copernicium 285|Nh Nihonium 286|Fl Flerovium 289|Mc Moscovium 290|Lv Livermorium 293|Ts Tennessine 294|Og Oganesson 294";

    const GROUPS = {
        alkali: [3, 11, 19, 37, 55, 87],
        alkaline: [4, 12, 20, 38, 56, 88],
        noble: [2, 10, 18, 36, 54, 86, 118],
        halogen: [9, 17, 35, 53, 85, 117],
        metalloid: [5, 14, 32, 33, 51, 52],
        nonmetal: [1, 6, 7, 8, 15, 16, 34],
        post: [13, 31, 49, 50, 81, 82, 83, 84, 113, 114, 115, 116],
    };

    function category(z) {
        for (const key of Object.keys(GROUPS)) if (GROUPS[key].includes(z)) return key;

        if (z >= 57 && z <= 71) return "lanthanide";
        if (z >= 89 && z <= 103) return "actinide";

        return "transition";
    }

    /* Grid cell (row 1-9, column 1-18); lanthanides and actinides sit in rows 8-9. */
    function position(z) {
        if (z === 1) return [1, 1];
        if (z === 2) return [1, 18];
        if (z <= 4) return [2, z - 2];
        if (z <= 10) return [2, z + 8];
        if (z <= 12) return [3, z - 10];
        if (z <= 18) return [3, z - 0];
        if (z <= 36) return [4, z - 18];
        if (z <= 54) return [5, z - 36];
        if (z <= 56) return [6, z - 54];
        if (z <= 71) return [8, z - 54];
        if (z <= 86) return [6, z - 68];
        if (z <= 88) return [7, z - 86];
        if (z <= 103) return [9, z - 86];

        return [7, z - 100];
    }

    const list = RAW.split("|").map((item, i) => {
        const [symbol, name, mass] = item.split(" ");
        const z = i + 1;
        const [row, col] = position(z);

        return {z, symbol, name, mass: Number(mass), radioactive: z === 43 || z === 61 || z >= 84 && ![90, 91, 92].includes(z), category: category(z), row, col};
    });
    const bySymbol = {};

    list.forEach(e => { bySymbol[e.symbol] = e; });

    /* Molar mass of a formula such as C6H12O6, Ca(OH)2 or CuSO4·5H2O. */
    function molarMass(formula) {
        const text = String(formula || "").replace(/\s+/g, "");

        if (!text) return {error: "Enter a formula."};

        const parts = text.split(/[·.*]/);
        let total = 0;

        for (const part of parts) {
            const m = /^(\d+)?(.*)$/.exec(part);
            const factor = m[1] ? Number(m[1]) : 1;
            const counts = parse(m[2]);

            if (counts.error) return counts;

            for (const [symbol, n] of Object.entries(counts)) total += bySymbol[symbol].mass * n * factor;
        }

        return {mass: total};
    }

    function parse(text) {
        let i = 0;

        function group() {
            const counts = {};

            while (i < text.length && text[i] !== ")") {
                if (text[i] === "(") {
                    i += 1;

                    const inner = group();

                    if (inner.error) return inner;
                    if (text[i] !== ")") return {error: "Missing closing parenthesis."};

                    i += 1;

                    const k = number();

                    Object.entries(inner).forEach(([s, n]) => { counts[s] = (counts[s] || 0) + n * k; });
                } else {
                    const m = /^[A-Z][a-z]?/.exec(text.slice(i));

                    if (!m) return {error: `Unexpected "${text[i]}".`};
                    if (!bySymbol[m[0]]) return {error: `Unknown element ${m[0]}.`};

                    i += m[0].length;
                    counts[m[0]] = (counts[m[0]] || 0) + number();
                }
            }

            return counts;
        }

        function number() {
            const m = /^\d+/.exec(text.slice(i));

            if (!m) return 1;

            i += m[0].length;

            return Number(m[0]);
        }

        const out = group();

        if (!out.error && i < text.length) return {error: "Unbalanced parentheses."};

        return out;
    }

    return {list, bySymbol, molarMass, category};
});
