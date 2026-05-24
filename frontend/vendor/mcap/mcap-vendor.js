var RCTMcapVendor = (() => {
  var __defProp = Object.defineProperty;
  var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
  var __getOwnPropNames = Object.getOwnPropertyNames;
  var __hasOwnProp = Object.prototype.hasOwnProperty;
  var __typeError = (msg) => {
    throw TypeError(msg);
  };
  var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
  var __export = (target, all) => {
    for (var name in all)
      __defProp(target, name, { get: all[name], enumerable: true });
  };
  var __copyProps = (to, from, except, desc) => {
    if (from && typeof from === "object" || typeof from === "function") {
      for (let key of __getOwnPropNames(from))
        if (!__hasOwnProp.call(to, key) && key !== except)
          __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
    }
    return to;
  };
  var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);
  var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);
  var __accessCheck = (obj, member, msg) => member.has(obj) || __typeError("Cannot " + msg);
  var __privateGet = (obj, member, getter) => (__accessCheck(obj, member, "read from private field"), getter ? getter.call(obj) : member.get(obj));
  var __privateAdd = (obj, member, value) => member.has(obj) ? __typeError("Cannot add the same private member more than once") : member instanceof WeakSet ? member.add(obj) : member.set(obj, value);
  var __privateSet = (obj, member, value, setter) => (__accessCheck(obj, member, "write to private field"), setter ? setter.call(obj, value) : member.set(obj, value), value);
  var __privateMethod = (obj, member, method) => (__accessCheck(obj, member, "access private method"), method);
  var __privateWrapper = (obj, member, setter, getter) => ({
    set _(value) {
      __privateSet(obj, member, value, setter);
    },
    get _() {
      return __privateGet(obj, member, getter);
    }
  });

  // mcap-vendor-entry.js
  var mcap_vendor_entry_exports = {};
  __export(mcap_vendor_entry_exports, {
    BlobReadable: () => BlobReadable,
    McapIndexedReader: () => McapIndexedReader
  });

  // node_modules/@foxglove/crc/dist/esm/src/index.js
  function crc32GenerateTables({ polynomial, numTables }) {
    const table = new Uint32Array(256 * numTables);
    for (let i = 0; i < 256; i++) {
      let r = i;
      r = (r & 1) * polynomial ^ r >>> 1;
      r = (r & 1) * polynomial ^ r >>> 1;
      r = (r & 1) * polynomial ^ r >>> 1;
      r = (r & 1) * polynomial ^ r >>> 1;
      r = (r & 1) * polynomial ^ r >>> 1;
      r = (r & 1) * polynomial ^ r >>> 1;
      r = (r & 1) * polynomial ^ r >>> 1;
      r = (r & 1) * polynomial ^ r >>> 1;
      table[i] = r;
    }
    for (let i = 256; i < table.length; i++) {
      const value = table[i - 256];
      table[i] = table[value & 255] ^ value >>> 8;
    }
    return table;
  }
  var CRC32_TABLE = crc32GenerateTables({ polynomial: 3988292384, numTables: 8 });
  function crc32Init() {
    return ~0;
  }
  function crc32Update(prev, data) {
    const byteLength = data.byteLength;
    const view = new DataView(data.buffer, data.byteOffset, byteLength);
    let r = prev;
    let offset = 0;
    const toAlign = -view.byteOffset & 3;
    for (; offset < toAlign && offset < byteLength; offset++) {
      r = CRC32_TABLE[(r ^ view.getUint8(offset)) & 255] ^ r >>> 8;
    }
    if (offset === byteLength) {
      return r;
    }
    offset = toAlign;
    let remainingBytes = byteLength - offset;
    for (; remainingBytes >= 8; offset += 8, remainingBytes -= 8) {
      r ^= view.getUint32(offset, true);
      const r2 = view.getUint32(offset + 4, true);
      r = CRC32_TABLE[0 * 256 + (r2 >>> 24 & 255)] ^ CRC32_TABLE[1 * 256 + (r2 >>> 16 & 255)] ^ CRC32_TABLE[2 * 256 + (r2 >>> 8 & 255)] ^ CRC32_TABLE[3 * 256 + (r2 >>> 0 & 255)] ^ CRC32_TABLE[4 * 256 + (r >>> 24 & 255)] ^ CRC32_TABLE[5 * 256 + (r >>> 16 & 255)] ^ CRC32_TABLE[6 * 256 + (r >>> 8 & 255)] ^ CRC32_TABLE[7 * 256 + (r >>> 0 & 255)];
    }
    for (let i = offset; i < byteLength; i++) {
      r = CRC32_TABLE[(r ^ view.getUint8(i)) & 255] ^ r >>> 8;
    }
    return r;
  }
  function crc32Final(prev) {
    return (prev ^ ~0) >>> 0;
  }
  function crc32(data) {
    return crc32Final(crc32Update(crc32Init(), data));
  }

  // node_modules/heap-js/dist/heap-js.es5.js
  var __awaiter = function(thisArg, _arguments, P, generator) {
    function adopt(value) {
      return value instanceof P ? value : new P(function(resolve) {
        resolve(value);
      });
    }
    return new (P || (P = Promise))(function(resolve, reject) {
      function fulfilled(value) {
        try {
          step(generator.next(value));
        } catch (e) {
          reject(e);
        }
      }
      function rejected(value) {
        try {
          step(generator["throw"](value));
        } catch (e) {
          reject(e);
        }
      }
      function step(result) {
        result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected);
      }
      step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
  };
  var __generator$1 = function(thisArg, body) {
    var _ = { label: 0, sent: function() {
      if (t[0] & 1) throw t[1];
      return t[1];
    }, trys: [], ops: [] }, f, y, t, g = Object.create((typeof Iterator === "function" ? Iterator : Object).prototype);
    return g.next = verb(0), g["throw"] = verb(1), g["return"] = verb(2), typeof Symbol === "function" && (g[Symbol.iterator] = function() {
      return this;
    }), g;
    function verb(n) {
      return function(v) {
        return step([n, v]);
      };
    }
    function step(op) {
      if (f) throw new TypeError("Generator is already executing.");
      while (g && (g = 0, op[0] && (_ = 0)), _) try {
        if (f = 1, y && (t = op[0] & 2 ? y["return"] : op[0] ? y["throw"] || ((t = y["return"]) && t.call(y), 0) : y.next) && !(t = t.call(y, op[1])).done) return t;
        if (y = 0, t) op = [op[0] & 2, t.value];
        switch (op[0]) {
          case 0:
          case 1:
            t = op;
            break;
          case 4:
            _.label++;
            return { value: op[1], done: false };
          case 5:
            _.label++;
            y = op[1];
            op = [0];
            continue;
          case 7:
            op = _.ops.pop();
            _.trys.pop();
            continue;
          default:
            if (!(t = _.trys, t = t.length > 0 && t[t.length - 1]) && (op[0] === 6 || op[0] === 2)) {
              _ = 0;
              continue;
            }
            if (op[0] === 3 && (!t || op[1] > t[0] && op[1] < t[3])) {
              _.label = op[1];
              break;
            }
            if (op[0] === 6 && _.label < t[1]) {
              _.label = t[1];
              t = op;
              break;
            }
            if (t && _.label < t[2]) {
              _.label = t[2];
              _.ops.push(op);
              break;
            }
            if (t[2]) _.ops.pop();
            _.trys.pop();
            continue;
        }
        op = body.call(thisArg, _);
      } catch (e) {
        op = [6, e];
        y = 0;
      } finally {
        f = t = 0;
      }
      if (op[0] & 5) throw op[1];
      return { value: op[0] ? op[1] : void 0, done: true };
    }
  };
  var __read$1 = function(o, n) {
    var m = typeof Symbol === "function" && o[Symbol.iterator];
    if (!m) return o;
    var i = m.call(o), r, ar = [], e;
    try {
      while ((n === void 0 || n-- > 0) && !(r = i.next()).done) ar.push(r.value);
    } catch (error) {
      e = { error };
    } finally {
      try {
        if (r && !r.done && (m = i["return"])) m.call(i);
      } finally {
        if (e) throw e.error;
      }
    }
    return ar;
  };
  var __spreadArray$1 = function(to, from, pack) {
    if (pack || arguments.length === 2) for (var i = 0, l = from.length, ar; i < l; i++) {
      if (ar || !(i in from)) {
        if (!ar) ar = Array.prototype.slice.call(from, 0, i);
        ar[i] = from[i];
      }
    }
    return to.concat(ar || Array.prototype.slice.call(from));
  };
  var __values = function(o) {
    var s = typeof Symbol === "function" && Symbol.iterator, m = s && o[s], i = 0;
    if (m) return m.call(o);
    if (o && typeof o.length === "number") return {
      next: function() {
        if (o && i >= o.length) o = void 0;
        return { value: o && o[i++], done: !o };
      }
    };
    throw new TypeError(s ? "Object is not iterable." : "Symbol.iterator is not defined.");
  };
  var HeapAsync = (
    /** @class */
    (function() {
      function HeapAsync2(compare) {
        if (compare === void 0) {
          compare = HeapAsync2.minComparator;
        }
        var _this = this;
        this.compare = compare;
        this.heapArray = [];
        this._limit = 0;
        this.offer = this.add;
        this.element = this.peek;
        this.poll = this.pop;
        this._invertedCompare = function(a, b) {
          return _this.compare(a, b).then(function(res) {
            return -1 * res;
          });
        };
      }
      HeapAsync2.getChildrenIndexOf = function(idx) {
        return [idx * 2 + 1, idx * 2 + 2];
      };
      HeapAsync2.getParentIndexOf = function(idx) {
        if (idx <= 0) {
          return -1;
        }
        var whichChildren = idx % 2 ? 1 : 2;
        return Math.floor((idx - whichChildren) / 2);
      };
      HeapAsync2.getSiblingIndexOf = function(idx) {
        if (idx <= 0) {
          return -1;
        }
        var whichChildren = idx % 2 ? 1 : -1;
        return idx + whichChildren;
      };
      HeapAsync2.minComparator = function(a, b) {
        return __awaiter(this, void 0, void 0, function() {
          return __generator$1(this, function(_a) {
            if (a > b) {
              return [2, 1];
            } else if (a < b) {
              return [2, -1];
            } else {
              return [2, 0];
            }
          });
        });
      };
      HeapAsync2.maxComparator = function(a, b) {
        return __awaiter(this, void 0, void 0, function() {
          return __generator$1(this, function(_a) {
            if (b > a) {
              return [2, 1];
            } else if (b < a) {
              return [2, -1];
            } else {
              return [2, 0];
            }
          });
        });
      };
      HeapAsync2.minComparatorNumber = function(a, b) {
        return __awaiter(this, void 0, void 0, function() {
          return __generator$1(this, function(_a) {
            return [2, a - b];
          });
        });
      };
      HeapAsync2.maxComparatorNumber = function(a, b) {
        return __awaiter(this, void 0, void 0, function() {
          return __generator$1(this, function(_a) {
            return [2, b - a];
          });
        });
      };
      HeapAsync2.defaultIsEqual = function(a, b) {
        return __awaiter(this, void 0, void 0, function() {
          return __generator$1(this, function(_a) {
            return [2, a === b];
          });
        });
      };
      HeapAsync2.print = function(heap) {
        function deep(i2) {
          var pi = HeapAsync2.getParentIndexOf(i2);
          return Math.floor(Math.log2(pi + 1));
        }
        function repeat(str, times) {
          var out = "";
          for (; times > 0; --times) {
            out += str;
          }
          return out;
        }
        var node = 0;
        var lines = [];
        var maxLines = deep(heap.length - 1) + 2;
        var maxLength = 0;
        while (node < heap.length) {
          var i = deep(node) + 1;
          if (node === 0) {
            i = 0;
          }
          var nodeText = String(heap.get(node));
          if (nodeText.length > maxLength) {
            maxLength = nodeText.length;
          }
          lines[i] = lines[i] || [];
          lines[i].push(nodeText);
          node += 1;
        }
        return lines.map(function(line, i2) {
          var times = Math.pow(2, maxLines - i2) - 1;
          return repeat(" ", Math.floor(times / 2) * maxLength) + line.map(function(el) {
            var half = (maxLength - el.length) / 2;
            return repeat(" ", Math.ceil(half)) + el + repeat(" ", Math.floor(half));
          }).join(repeat(" ", times * maxLength));
        }).join("\n");
      };
      HeapAsync2.heapify = function(arr, compare) {
        return __awaiter(this, void 0, void 0, function() {
          var heap;
          return __generator$1(this, function(_a) {
            switch (_a.label) {
              case 0:
                heap = new HeapAsync2(compare);
                heap.heapArray = arr;
                return [4, heap.init()];
              case 1:
                _a.sent();
                return [2, heap];
            }
          });
        });
      };
      HeapAsync2.heappop = function(heapArr, compare) {
        var heap = new HeapAsync2(compare);
        heap.heapArray = heapArr;
        return heap.pop();
      };
      HeapAsync2.heappush = function(heapArr, item, compare) {
        return __awaiter(this, void 0, void 0, function() {
          var heap;
          return __generator$1(this, function(_a) {
            switch (_a.label) {
              case 0:
                heap = new HeapAsync2(compare);
                heap.heapArray = heapArr;
                return [4, heap.push(item)];
              case 1:
                _a.sent();
                return [
                  2
                  /*return*/
                ];
            }
          });
        });
      };
      HeapAsync2.heappushpop = function(heapArr, item, compare) {
        var heap = new HeapAsync2(compare);
        heap.heapArray = heapArr;
        return heap.pushpop(item);
      };
      HeapAsync2.heapreplace = function(heapArr, item, compare) {
        var heap = new HeapAsync2(compare);
        heap.heapArray = heapArr;
        return heap.replace(item);
      };
      HeapAsync2.heaptop = function(heapArr, n, compare) {
        if (n === void 0) {
          n = 1;
        }
        var heap = new HeapAsync2(compare);
        heap.heapArray = heapArr;
        return heap.top(n);
      };
      HeapAsync2.heapbottom = function(heapArr, n, compare) {
        if (n === void 0) {
          n = 1;
        }
        var heap = new HeapAsync2(compare);
        heap.heapArray = heapArr;
        return heap.bottom(n);
      };
      HeapAsync2.nlargest = function(n, iterable, compare) {
        return __awaiter(this, void 0, void 0, function() {
          var heap;
          return __generator$1(this, function(_a) {
            switch (_a.label) {
              case 0:
                heap = new HeapAsync2(compare);
                heap.heapArray = __spreadArray$1([], __read$1(iterable), false);
                return [4, heap.init()];
              case 1:
                _a.sent();
                return [2, heap.top(n)];
            }
          });
        });
      };
      HeapAsync2.nsmallest = function(n, iterable, compare) {
        return __awaiter(this, void 0, void 0, function() {
          var heap;
          return __generator$1(this, function(_a) {
            switch (_a.label) {
              case 0:
                heap = new HeapAsync2(compare);
                heap.heapArray = __spreadArray$1([], __read$1(iterable), false);
                return [4, heap.init()];
              case 1:
                _a.sent();
                return [2, heap.bottom(n)];
            }
          });
        });
      };
      HeapAsync2.prototype.add = function(element) {
        return __awaiter(this, void 0, void 0, function() {
          return __generator$1(this, function(_a) {
            switch (_a.label) {
              case 0:
                return [4, this._sortNodeUp(this.heapArray.push(element) - 1)];
              case 1:
                _a.sent();
                this._applyLimit();
                return [2, true];
            }
          });
        });
      };
      HeapAsync2.prototype.addAll = function(elements) {
        return __awaiter(this, void 0, void 0, function() {
          var i, l;
          var _a;
          return __generator$1(this, function(_b) {
            switch (_b.label) {
              case 0:
                i = this.length;
                (_a = this.heapArray).push.apply(_a, __spreadArray$1([], __read$1(elements), false));
                l = this.length;
                _b.label = 1;
              case 1:
                if (!(i < l)) return [3, 4];
                return [4, this._sortNodeUp(i)];
              case 2:
                _b.sent();
                _b.label = 3;
              case 3:
                ++i;
                return [3, 1];
              case 4:
                this._applyLimit();
                return [2, true];
            }
          });
        });
      };
      HeapAsync2.prototype.bottom = function() {
        return __awaiter(this, arguments, void 0, function(n) {
          if (n === void 0) {
            n = 1;
          }
          return __generator$1(this, function(_a) {
            if (this.heapArray.length === 0 || n <= 0) {
              return [2, []];
            } else if (this.heapArray.length === 1) {
              return [2, [this.heapArray[0]]];
            } else if (n >= this.heapArray.length) {
              return [2, __spreadArray$1([], __read$1(this.heapArray), false)];
            } else {
              return [2, this._bottomN_push(~~n)];
            }
          });
        });
      };
      HeapAsync2.prototype.check = function() {
        return __awaiter(this, void 0, void 0, function() {
          var j, el, children, children_1, children_1_1, ch, e_1_1;
          var e_1, _a;
          return __generator$1(this, function(_b) {
            switch (_b.label) {
              case 0:
                j = 0;
                _b.label = 1;
              case 1:
                if (!(j < this.heapArray.length)) return [3, 10];
                el = this.heapArray[j];
                children = this.getChildrenOf(j);
                _b.label = 2;
              case 2:
                _b.trys.push([2, 7, 8, 9]);
                children_1 = (e_1 = void 0, __values(children)), children_1_1 = children_1.next();
                _b.label = 3;
              case 3:
                if (!!children_1_1.done) return [3, 6];
                ch = children_1_1.value;
                return [4, this.compare(el, ch)];
              case 4:
                if (_b.sent() > 0) {
                  return [2, el];
                }
                _b.label = 5;
              case 5:
                children_1_1 = children_1.next();
                return [3, 3];
              case 6:
                return [3, 9];
              case 7:
                e_1_1 = _b.sent();
                e_1 = { error: e_1_1 };
                return [3, 9];
              case 8:
                try {
                  if (children_1_1 && !children_1_1.done && (_a = children_1.return)) _a.call(children_1);
                } finally {
                  if (e_1) throw e_1.error;
                }
                return [
                  7
                  /*endfinally*/
                ];
              case 9:
                ++j;
                return [3, 1];
              case 10:
                return [
                  2
                  /*return*/
                ];
            }
          });
        });
      };
      HeapAsync2.prototype.clear = function() {
        this.heapArray = [];
      };
      HeapAsync2.prototype.clone = function() {
        var cloned = new HeapAsync2(this.comparator());
        cloned.heapArray = this.toArray();
        cloned._limit = this._limit;
        return cloned;
      };
      HeapAsync2.prototype.comparator = function() {
        return this.compare;
      };
      HeapAsync2.prototype.contains = function(o_1) {
        return __awaiter(this, arguments, void 0, function(o, fn) {
          var _a, _b, el, e_2_1;
          var e_2, _c;
          if (fn === void 0) {
            fn = HeapAsync2.defaultIsEqual;
          }
          return __generator$1(this, function(_d) {
            switch (_d.label) {
              case 0:
                _d.trys.push([0, 5, 6, 7]);
                _a = __values(this.heapArray), _b = _a.next();
                _d.label = 1;
              case 1:
                if (!!_b.done) return [3, 4];
                el = _b.value;
                return [4, fn(el, o)];
              case 2:
                if (_d.sent()) {
                  return [2, true];
                }
                _d.label = 3;
              case 3:
                _b = _a.next();
                return [3, 1];
              case 4:
                return [3, 7];
              case 5:
                e_2_1 = _d.sent();
                e_2 = { error: e_2_1 };
                return [3, 7];
              case 6:
                try {
                  if (_b && !_b.done && (_c = _a.return)) _c.call(_a);
                } finally {
                  if (e_2) throw e_2.error;
                }
                return [
                  7
                  /*endfinally*/
                ];
              case 7:
                return [2, false];
            }
          });
        });
      };
      HeapAsync2.prototype.init = function(array) {
        return __awaiter(this, void 0, void 0, function() {
          var i;
          return __generator$1(this, function(_a) {
            switch (_a.label) {
              case 0:
                if (array) {
                  this.heapArray = __spreadArray$1([], __read$1(array), false);
                }
                i = HeapAsync2.getParentIndexOf(this.length - 1);
                _a.label = 1;
              case 1:
                if (!(i >= 0)) return [3, 4];
                return [4, this._sortNodeDown(i)];
              case 2:
                _a.sent();
                _a.label = 3;
              case 3:
                --i;
                return [3, 1];
              case 4:
                this._applyLimit();
                return [
                  2
                  /*return*/
                ];
            }
          });
        });
      };
      HeapAsync2.prototype.isEmpty = function() {
        return this.length === 0;
      };
      HeapAsync2.prototype.leafs = function() {
        if (this.heapArray.length === 0) {
          return [];
        }
        var pi = HeapAsync2.getParentIndexOf(this.heapArray.length - 1);
        return this.heapArray.slice(pi + 1);
      };
      Object.defineProperty(HeapAsync2.prototype, "length", {
        /**
         * Length of the heap.
         * @return {Number}
         */
        get: function() {
          return this.heapArray.length;
        },
        enumerable: false,
        configurable: true
      });
      Object.defineProperty(HeapAsync2.prototype, "limit", {
        /**
         * Get length limit of the heap.
         * @return {Number}
         */
        get: function() {
          return this._limit;
        },
        /**
         * Set length limit of the heap.
         * @return {Number}
         */
        set: function(_l) {
          this._limit = ~~_l;
          this._applyLimit();
        },
        enumerable: false,
        configurable: true
      });
      HeapAsync2.prototype.peek = function() {
        return this.heapArray[0];
      };
      HeapAsync2.prototype.pop = function() {
        return __awaiter(this, void 0, void 0, function() {
          var last;
          return __generator$1(this, function(_a) {
            last = this.heapArray.pop();
            if (this.length > 0 && last !== void 0) {
              return [2, this.replace(last)];
            }
            return [2, last];
          });
        });
      };
      HeapAsync2.prototype.push = function() {
        var elements = [];
        for (var _i = 0; _i < arguments.length; _i++) {
          elements[_i] = arguments[_i];
        }
        return __awaiter(this, void 0, void 0, function() {
          return __generator$1(this, function(_a) {
            if (elements.length < 1) {
              return [2, false];
            } else if (elements.length === 1) {
              return [2, this.add(elements[0])];
            } else {
              return [2, this.addAll(elements)];
            }
          });
        });
      };
      HeapAsync2.prototype.pushpop = function(element) {
        return __awaiter(this, void 0, void 0, function() {
          var _a;
          return __generator$1(this, function(_b) {
            switch (_b.label) {
              case 0:
                return [4, this.compare(this.heapArray[0], element)];
              case 1:
                if (!(_b.sent() < 0)) return [3, 3];
                _a = __read$1([this.heapArray[0], element], 2), element = _a[0], this.heapArray[0] = _a[1];
                return [4, this._sortNodeDown(0)];
              case 2:
                _b.sent();
                _b.label = 3;
              case 3:
                return [2, element];
            }
          });
        });
      };
      HeapAsync2.prototype.remove = function(o_1) {
        return __awaiter(this, arguments, void 0, function(o, fn) {
          var queue, idx, children;
          var _this = this;
          if (fn === void 0) {
            fn = HeapAsync2.defaultIsEqual;
          }
          return __generator$1(this, function(_a) {
            switch (_a.label) {
              case 0:
                if (!this.heapArray.length)
                  return [2, false];
                if (!(o === void 0)) return [3, 2];
                return [4, this.pop()];
              case 1:
                _a.sent();
                return [2, true];
              case 2:
                queue = [0];
                _a.label = 3;
              case 3:
                if (!queue.length) return [3, 13];
                idx = queue.shift();
                return [4, fn(this.heapArray[idx], o)];
              case 4:
                if (!_a.sent()) return [3, 11];
                if (!(idx === 0)) return [3, 6];
                return [4, this.pop()];
              case 5:
                _a.sent();
                return [3, 10];
              case 6:
                if (!(idx === this.heapArray.length - 1)) return [3, 7];
                this.heapArray.pop();
                return [3, 10];
              case 7:
                this.heapArray.splice(idx, 1, this.heapArray.pop());
                return [4, this._sortNodeUp(idx)];
              case 8:
                _a.sent();
                return [4, this._sortNodeDown(idx)];
              case 9:
                _a.sent();
                _a.label = 10;
              case 10:
                return [2, true];
              case 11:
                children = HeapAsync2.getChildrenIndexOf(idx).filter(function(c) {
                  return c < _this.heapArray.length;
                });
                queue.push.apply(queue, __spreadArray$1([], __read$1(children), false));
                _a.label = 12;
              case 12:
                return [3, 3];
              case 13:
                return [2, false];
            }
          });
        });
      };
      HeapAsync2.prototype.replace = function(element) {
        return __awaiter(this, void 0, void 0, function() {
          var peek;
          return __generator$1(this, function(_a) {
            switch (_a.label) {
              case 0:
                peek = this.heapArray[0];
                this.heapArray[0] = element;
                return [4, this._sortNodeDown(0)];
              case 1:
                _a.sent();
                return [2, peek];
            }
          });
        });
      };
      HeapAsync2.prototype.size = function() {
        return this.length;
      };
      HeapAsync2.prototype.top = function() {
        return __awaiter(this, arguments, void 0, function(n) {
          if (n === void 0) {
            n = 1;
          }
          return __generator$1(this, function(_a) {
            if (this.heapArray.length === 0 || n <= 0) {
              return [2, []];
            } else if (this.heapArray.length === 1 || n === 1) {
              return [2, [this.heapArray[0]]];
            } else if (n >= this.heapArray.length) {
              return [2, __spreadArray$1([], __read$1(this.heapArray), false)];
            } else {
              return [2, this._topN_push(~~n)];
            }
          });
        });
      };
      HeapAsync2.prototype.toArray = function() {
        return __spreadArray$1([], __read$1(this.heapArray), false);
      };
      HeapAsync2.prototype.toString = function() {
        return this.heapArray.toString();
      };
      HeapAsync2.prototype.get = function(i) {
        return this.heapArray[i];
      };
      HeapAsync2.prototype.getChildrenOf = function(idx) {
        var _this = this;
        return HeapAsync2.getChildrenIndexOf(idx).map(function(i) {
          return _this.heapArray[i];
        }).filter(function(e) {
          return e !== void 0;
        });
      };
      HeapAsync2.prototype.getParentOf = function(idx) {
        var pi = HeapAsync2.getParentIndexOf(idx);
        return this.heapArray[pi];
      };
      HeapAsync2.prototype[Symbol.iterator] = function() {
        return __generator$1(this, function(_a) {
          switch (_a.label) {
            case 0:
              if (!this.length) return [3, 2];
              return [4, this.pop()];
            case 1:
              _a.sent();
              return [3, 0];
            case 2:
              return [
                2
                /*return*/
              ];
          }
        });
      };
      HeapAsync2.prototype.iterator = function() {
        return this;
      };
      HeapAsync2.prototype._applyLimit = function() {
        if (this._limit && this._limit < this.heapArray.length) {
          var rm = this.heapArray.length - this._limit;
          while (rm) {
            this.heapArray.pop();
            --rm;
          }
        }
      };
      HeapAsync2.prototype._bottomN_push = function(n) {
        return __awaiter(this, void 0, void 0, function() {
          var bottomHeap, startAt, parentStartAt, indices, i, arr, i;
          return __generator$1(this, function(_a) {
            switch (_a.label) {
              case 0:
                bottomHeap = new HeapAsync2(this.compare);
                bottomHeap.limit = n;
                bottomHeap.heapArray = this.heapArray.slice(-n);
                return [4, bottomHeap.init()];
              case 1:
                _a.sent();
                startAt = this.heapArray.length - 1 - n;
                parentStartAt = HeapAsync2.getParentIndexOf(startAt);
                indices = [];
                for (i = startAt; i > parentStartAt; --i) {
                  indices.push(i);
                }
                arr = this.heapArray;
                _a.label = 2;
              case 2:
                if (!indices.length) return [3, 6];
                i = indices.shift();
                return [4, this.compare(arr[i], bottomHeap.peek())];
              case 3:
                if (!(_a.sent() > 0)) return [3, 5];
                return [4, bottomHeap.replace(arr[i])];
              case 4:
                _a.sent();
                if (i % 2) {
                  indices.push(HeapAsync2.getParentIndexOf(i));
                }
                _a.label = 5;
              case 5:
                return [3, 2];
              case 6:
                return [2, bottomHeap.toArray()];
            }
          });
        });
      };
      HeapAsync2.prototype._moveNode = function(j, k) {
        var temp = this.heapArray[j];
        this.heapArray[j] = this.heapArray[k];
        this.heapArray[k] = temp;
      };
      HeapAsync2.prototype._sortNodeDown = function(i) {
        return __awaiter(this, void 0, void 0, function() {
          var length, originalIndex, value, left, right, best, _a;
          return __generator$1(this, function(_b) {
            switch (_b.label) {
              case 0:
                length = this.heapArray.length;
                originalIndex = i;
                value = this.heapArray[i];
                left = 2 * i + 1;
                _b.label = 1;
              case 1:
                if (!(left < length)) return [3, 5];
                right = left + 1;
                _a = right >= length;
                if (_a) return [3, 3];
                return [4, this.compare(this.heapArray[left], this.heapArray[right])];
              case 2:
                _a = _b.sent() < 0;
                _b.label = 3;
              case 3:
                best = _a ? left : right;
                return [4, this.compare(this.heapArray[best], value)];
              case 4:
                if (_b.sent() < 0) {
                  this.heapArray[i] = this.heapArray[best];
                  i = best;
                  left = 2 * i + 1;
                } else
                  return [3, 5];
                return [3, 1];
              case 5:
                if (i !== originalIndex) {
                  this.heapArray[i] = value;
                }
                return [
                  2
                  /*return*/
                ];
            }
          });
        });
      };
      HeapAsync2.prototype._sortNodeUp = function(i) {
        return __awaiter(this, void 0, void 0, function() {
          var value, originalIndex, pi;
          return __generator$1(this, function(_a) {
            switch (_a.label) {
              case 0:
                value = this.heapArray[i];
                originalIndex = i;
                _a.label = 1;
              case 1:
                if (!(i > 0)) return [3, 3];
                pi = HeapAsync2.getParentIndexOf(i);
                return [4, this.compare(value, this.heapArray[pi])];
              case 2:
                if (_a.sent() < 0) {
                  this.heapArray[i] = this.heapArray[pi];
                  i = pi;
                } else
                  return [3, 3];
                return [3, 1];
              case 3:
                if (i !== originalIndex) {
                  this.heapArray[i] = value;
                }
                return [
                  2
                  /*return*/
                ];
            }
          });
        });
      };
      HeapAsync2.prototype._topN_push = function(n) {
        return __awaiter(this, void 0, void 0, function() {
          var topHeap, indices, arr, i;
          return __generator$1(this, function(_a) {
            switch (_a.label) {
              case 0:
                topHeap = new HeapAsync2(this._invertedCompare);
                topHeap.limit = n;
                indices = [0];
                arr = this.heapArray;
                _a.label = 1;
              case 1:
                if (!indices.length) return [3, 7];
                i = indices.shift();
                if (!(i < arr.length)) return [3, 6];
                if (!(topHeap.length < n)) return [3, 3];
                return [4, topHeap.push(arr[i])];
              case 2:
                _a.sent();
                indices.push.apply(indices, __spreadArray$1([], __read$1(HeapAsync2.getChildrenIndexOf(i)), false));
                return [3, 6];
              case 3:
                return [4, this.compare(arr[i], topHeap.peek())];
              case 4:
                if (!(_a.sent() < 0)) return [3, 6];
                return [4, topHeap.replace(arr[i])];
              case 5:
                _a.sent();
                indices.push.apply(indices, __spreadArray$1([], __read$1(HeapAsync2.getChildrenIndexOf(i)), false));
                _a.label = 6;
              case 6:
                return [3, 1];
              case 7:
                return [2, topHeap.toArray()];
            }
          });
        });
      };
      HeapAsync2.prototype._topN_fill = function(n) {
        return __awaiter(this, void 0, void 0, function() {
          var heapArray, topHeap, branch, indices, i, i;
          return __generator$1(this, function(_a) {
            switch (_a.label) {
              case 0:
                heapArray = this.heapArray;
                topHeap = new HeapAsync2(this._invertedCompare);
                topHeap.limit = n;
                topHeap.heapArray = heapArray.slice(0, n);
                return [4, topHeap.init()];
              case 1:
                _a.sent();
                branch = HeapAsync2.getParentIndexOf(n - 1) + 1;
                indices = [];
                for (i = branch; i < n; ++i) {
                  indices.push.apply(indices, __spreadArray$1([], __read$1(HeapAsync2.getChildrenIndexOf(i).filter(function(l) {
                    return l < heapArray.length;
                  })), false));
                }
                if ((n - 1) % 2) {
                  indices.push(n);
                }
                _a.label = 2;
              case 2:
                if (!indices.length) return [3, 6];
                i = indices.shift();
                if (!(i < heapArray.length)) return [3, 5];
                return [4, this.compare(heapArray[i], topHeap.peek())];
              case 3:
                if (!(_a.sent() < 0)) return [3, 5];
                return [4, topHeap.replace(heapArray[i])];
              case 4:
                _a.sent();
                indices.push.apply(indices, __spreadArray$1([], __read$1(HeapAsync2.getChildrenIndexOf(i)), false));
                _a.label = 5;
              case 5:
                return [3, 2];
              case 6:
                return [2, topHeap.toArray()];
            }
          });
        });
      };
      HeapAsync2.prototype._topN_heap = function(n) {
        return __awaiter(this, void 0, void 0, function() {
          var topHeap, result, i, _a, _b;
          return __generator$1(this, function(_c) {
            switch (_c.label) {
              case 0:
                topHeap = this.clone();
                result = [];
                i = 0;
                _c.label = 1;
              case 1:
                if (!(i < n)) return [3, 4];
                _b = (_a = result).push;
                return [4, topHeap.pop()];
              case 2:
                _b.apply(_a, [_c.sent()]);
                _c.label = 3;
              case 3:
                ++i;
                return [3, 1];
              case 4:
                return [2, result];
            }
          });
        });
      };
      HeapAsync2.prototype._topIdxOf = function(list) {
        return __awaiter(this, void 0, void 0, function() {
          var idx, top, i, comp;
          return __generator$1(this, function(_a) {
            switch (_a.label) {
              case 0:
                if (!list.length) {
                  return [2, -1];
                }
                idx = 0;
                top = list[idx];
                i = 1;
                _a.label = 1;
              case 1:
                if (!(i < list.length)) return [3, 4];
                return [4, this.compare(list[i], top)];
              case 2:
                comp = _a.sent();
                if (comp < 0) {
                  idx = i;
                  top = list[i];
                }
                _a.label = 3;
              case 3:
                ++i;
                return [3, 1];
              case 4:
                return [2, idx];
            }
          });
        });
      };
      HeapAsync2.prototype._topOf = function() {
        var list = [];
        for (var _i = 0; _i < arguments.length; _i++) {
          list[_i] = arguments[_i];
        }
        return __awaiter(this, void 0, void 0, function() {
          var heap;
          return __generator$1(this, function(_a) {
            switch (_a.label) {
              case 0:
                heap = new HeapAsync2(this.compare);
                return [4, heap.init(list)];
              case 1:
                _a.sent();
                return [2, heap.peek()];
            }
          });
        });
      };
      return HeapAsync2;
    })()
  );
  var __generator = function(thisArg, body) {
    var _ = { label: 0, sent: function() {
      if (t[0] & 1) throw t[1];
      return t[1];
    }, trys: [], ops: [] }, f, y, t, g = Object.create((typeof Iterator === "function" ? Iterator : Object).prototype);
    return g.next = verb(0), g["throw"] = verb(1), g["return"] = verb(2), typeof Symbol === "function" && (g[Symbol.iterator] = function() {
      return this;
    }), g;
    function verb(n) {
      return function(v) {
        return step([n, v]);
      };
    }
    function step(op) {
      if (f) throw new TypeError("Generator is already executing.");
      while (g && (g = 0, op[0] && (_ = 0)), _) try {
        if (f = 1, y && (t = op[0] & 2 ? y["return"] : op[0] ? y["throw"] || ((t = y["return"]) && t.call(y), 0) : y.next) && !(t = t.call(y, op[1])).done) return t;
        if (y = 0, t) op = [op[0] & 2, t.value];
        switch (op[0]) {
          case 0:
          case 1:
            t = op;
            break;
          case 4:
            _.label++;
            return { value: op[1], done: false };
          case 5:
            _.label++;
            y = op[1];
            op = [0];
            continue;
          case 7:
            op = _.ops.pop();
            _.trys.pop();
            continue;
          default:
            if (!(t = _.trys, t = t.length > 0 && t[t.length - 1]) && (op[0] === 6 || op[0] === 2)) {
              _ = 0;
              continue;
            }
            if (op[0] === 3 && (!t || op[1] > t[0] && op[1] < t[3])) {
              _.label = op[1];
              break;
            }
            if (op[0] === 6 && _.label < t[1]) {
              _.label = t[1];
              t = op;
              break;
            }
            if (t && _.label < t[2]) {
              _.label = t[2];
              _.ops.push(op);
              break;
            }
            if (t[2]) _.ops.pop();
            _.trys.pop();
            continue;
        }
        op = body.call(thisArg, _);
      } catch (e) {
        op = [6, e];
        y = 0;
      } finally {
        f = t = 0;
      }
      if (op[0] & 5) throw op[1];
      return { value: op[0] ? op[1] : void 0, done: true };
    }
  };
  var __read = function(o, n) {
    var m = typeof Symbol === "function" && o[Symbol.iterator];
    if (!m) return o;
    var i = m.call(o), r, ar = [], e;
    try {
      while ((n === void 0 || n-- > 0) && !(r = i.next()).done) ar.push(r.value);
    } catch (error) {
      e = { error };
    } finally {
      try {
        if (r && !r.done && (m = i["return"])) m.call(i);
      } finally {
        if (e) throw e.error;
      }
    }
    return ar;
  };
  var __spreadArray = function(to, from, pack) {
    if (pack || arguments.length === 2) for (var i = 0, l = from.length, ar; i < l; i++) {
      if (ar || !(i in from)) {
        if (!ar) ar = Array.prototype.slice.call(from, 0, i);
        ar[i] = from[i];
      }
    }
    return to.concat(ar || Array.prototype.slice.call(from));
  };
  var Heap = (
    /** @class */
    (function() {
      function Heap2(compare) {
        if (compare === void 0) {
          compare = Heap2.minComparator;
        }
        var _this = this;
        this.compare = compare;
        this.heapArray = [];
        this._limit = 0;
        this.offer = this.add;
        this.element = this.peek;
        this.poll = this.pop;
        this.removeAll = this.clear;
        this._invertedCompare = function(a, b) {
          return -1 * _this.compare(a, b);
        };
      }
      Heap2.getChildrenIndexOf = function(idx) {
        return [idx * 2 + 1, idx * 2 + 2];
      };
      Heap2.getParentIndexOf = function(idx) {
        if (idx <= 0) {
          return -1;
        }
        return idx - 1 >> 1;
      };
      Heap2.getSiblingIndexOf = function(idx) {
        if (idx <= 0) {
          return -1;
        }
        var whichChildren = idx % 2 ? 1 : -1;
        return idx + whichChildren;
      };
      Heap2.minComparator = function(a, b) {
        if (a > b) {
          return 1;
        } else if (a < b) {
          return -1;
        } else {
          return 0;
        }
      };
      Heap2.maxComparator = function(a, b) {
        if (b > a) {
          return 1;
        } else if (b < a) {
          return -1;
        } else {
          return 0;
        }
      };
      Heap2.minComparatorNumber = function(a, b) {
        return a - b;
      };
      Heap2.maxComparatorNumber = function(a, b) {
        return b - a;
      };
      Heap2.defaultIsEqual = function(a, b) {
        return a === b;
      };
      Heap2.print = function(heap) {
        function deep(i2) {
          var pi = Heap2.getParentIndexOf(i2);
          return Math.floor(Math.log2(pi + 1));
        }
        function repeat(str, times) {
          var out = "";
          for (; times > 0; --times) {
            out += str;
          }
          return out;
        }
        var node = 0;
        var lines = [];
        var maxLines = deep(heap.length - 1) + 2;
        var maxLength = 0;
        while (node < heap.length) {
          var i = deep(node) + 1;
          if (node === 0) {
            i = 0;
          }
          var nodeText = String(heap.get(node));
          if (nodeText.length > maxLength) {
            maxLength = nodeText.length;
          }
          lines[i] = lines[i] || [];
          lines[i].push(nodeText);
          node += 1;
        }
        return lines.map(function(line, i2) {
          var times = Math.pow(2, maxLines - i2) - 1;
          return repeat(" ", Math.floor(times / 2) * maxLength) + line.map(function(el) {
            var half = (maxLength - el.length) / 2;
            return repeat(" ", Math.ceil(half)) + el + repeat(" ", Math.floor(half));
          }).join(repeat(" ", times * maxLength));
        }).join("\n");
      };
      Heap2.heapify = function(arr, compare) {
        var heap = new Heap2(compare);
        heap.heapArray = arr;
        heap.init();
        return heap;
      };
      Heap2.heappop = function(heapArr, compare) {
        var heap = new Heap2(compare);
        heap.heapArray = heapArr;
        return heap.pop();
      };
      Heap2.heappush = function(heapArr, item, compare) {
        var heap = new Heap2(compare);
        heap.heapArray = heapArr;
        heap.push(item);
      };
      Heap2.heappushpop = function(heapArr, item, compare) {
        var heap = new Heap2(compare);
        heap.heapArray = heapArr;
        return heap.pushpop(item);
      };
      Heap2.heapreplace = function(heapArr, item, compare) {
        var heap = new Heap2(compare);
        heap.heapArray = heapArr;
        return heap.replace(item);
      };
      Heap2.heaptop = function(heapArr, n, compare) {
        if (n === void 0) {
          n = 1;
        }
        var heap = new Heap2(compare);
        heap.heapArray = heapArr;
        return heap.top(n);
      };
      Heap2.heapbottom = function(heapArr, n, compare) {
        if (n === void 0) {
          n = 1;
        }
        var heap = new Heap2(compare);
        heap.heapArray = heapArr;
        return heap.bottom(n);
      };
      Heap2.nlargest = function(n, iterable, compare) {
        var heap = new Heap2(compare);
        heap.heapArray = __spreadArray([], __read(iterable), false);
        heap.init();
        return heap.top(n);
      };
      Heap2.nsmallest = function(n, iterable, compare) {
        var heap = new Heap2(compare);
        heap.heapArray = __spreadArray([], __read(iterable), false);
        heap.init();
        return heap.bottom(n);
      };
      Heap2.prototype.add = function(element) {
        this._sortNodeUp(this.heapArray.push(element) - 1);
        this._applyLimit();
        return true;
      };
      Heap2.prototype.addAll = function(elements) {
        var _a;
        var i = this.length;
        (_a = this.heapArray).push.apply(_a, __spreadArray([], __read(elements), false));
        for (var l = this.length; i < l; ++i) {
          this._sortNodeUp(i);
        }
        this._applyLimit();
        return true;
      };
      Heap2.prototype.bottom = function(n) {
        if (n === void 0) {
          n = 1;
        }
        if (this.heapArray.length === 0 || n <= 0) {
          return [];
        } else if (this.heapArray.length === 1) {
          return [this.heapArray[0]];
        } else if (n >= this.heapArray.length) {
          return __spreadArray([], __read(this.heapArray), false);
        } else {
          return this._bottomN_push(~~n);
        }
      };
      Heap2.prototype.check = function() {
        var _this = this;
        return this.heapArray.find(function(el, j) {
          return !!_this.getChildrenOf(j).find(function(ch) {
            return _this.compare(el, ch) > 0;
          });
        });
      };
      Heap2.prototype.clear = function() {
        this.heapArray = [];
      };
      Heap2.prototype.clone = function() {
        var cloned = new Heap2(this.comparator());
        cloned.heapArray = this.toArray();
        cloned._limit = this._limit;
        return cloned;
      };
      Heap2.prototype.comparator = function() {
        return this.compare;
      };
      Heap2.prototype.contains = function(o, callbackFn) {
        if (callbackFn === void 0) {
          callbackFn = Heap2.defaultIsEqual;
        }
        return this.indexOf(o, callbackFn) !== -1;
      };
      Heap2.prototype.init = function(array) {
        if (array) {
          this.heapArray = __spreadArray([], __read(array), false);
        }
        for (var i = Heap2.getParentIndexOf(this.length - 1); i >= 0; --i) {
          this._sortNodeDown(i);
        }
        this._applyLimit();
      };
      Heap2.prototype.isEmpty = function() {
        return this.length === 0;
      };
      Heap2.prototype.indexOf = function(element, callbackFn) {
        if (callbackFn === void 0) {
          callbackFn = Heap2.defaultIsEqual;
        }
        if (this.heapArray.length === 0) {
          return -1;
        }
        var indexes = [];
        var currentIndex = 0;
        while (currentIndex < this.heapArray.length) {
          var currentElement = this.heapArray[currentIndex];
          if (callbackFn(currentElement, element)) {
            return currentIndex;
          } else if (this.compare(currentElement, element) <= 0) {
            indexes.push.apply(indexes, __spreadArray([], __read(Heap2.getChildrenIndexOf(currentIndex)), false));
          }
          currentIndex = indexes.shift() || this.heapArray.length;
        }
        return -1;
      };
      Heap2.prototype.indexOfEvery = function(element, callbackFn) {
        if (callbackFn === void 0) {
          callbackFn = Heap2.defaultIsEqual;
        }
        if (this.heapArray.length === 0) {
          return [];
        }
        var indexes = [];
        var foundIndexes = [];
        var currentIndex = 0;
        while (currentIndex < this.heapArray.length) {
          var currentElement = this.heapArray[currentIndex];
          if (callbackFn(currentElement, element)) {
            foundIndexes.push(currentIndex);
            indexes.push.apply(indexes, __spreadArray([], __read(Heap2.getChildrenIndexOf(currentIndex)), false));
          } else if (this.compare(currentElement, element) <= 0) {
            indexes.push.apply(indexes, __spreadArray([], __read(Heap2.getChildrenIndexOf(currentIndex)), false));
          }
          currentIndex = indexes.shift() || this.heapArray.length;
        }
        return foundIndexes;
      };
      Heap2.prototype.leafs = function() {
        if (this.heapArray.length === 0) {
          return [];
        }
        var pi = Heap2.getParentIndexOf(this.heapArray.length - 1);
        return this.heapArray.slice(pi + 1);
      };
      Object.defineProperty(Heap2.prototype, "length", {
        /**
         * Length of the heap. Aliases: {@link size}.
         * @return {Number}
         * @see size
         */
        get: function() {
          return this.heapArray.length;
        },
        enumerable: false,
        configurable: true
      });
      Object.defineProperty(Heap2.prototype, "limit", {
        /**
         * Get length limit of the heap.
         * Use {@link setLimit} or {@link limit} to set the limit.
         * @return {Number}
         * @see setLimit
         */
        get: function() {
          return this._limit;
        },
        /**
         * Set length limit of the heap. Same as using {@link setLimit}.
         * @description If the heap is longer than the limit, the needed amount of leafs are removed.
         * @param {Number} _l Limit, defaults to 0 (no limit). Negative, Infinity, or NaN values set the limit to 0.
         * @see setLimit
         */
        set: function(_l) {
          if (_l < 0 || isNaN(_l)) {
            this._limit = 0;
          } else {
            this._limit = ~~_l;
          }
          this._applyLimit();
        },
        enumerable: false,
        configurable: true
      });
      Heap2.prototype.setLimit = function(_l) {
        this.limit = _l;
        if (_l < 0 || isNaN(_l)) {
          return NaN;
        } else {
          return this._limit;
        }
      };
      Heap2.prototype.peek = function() {
        return this.heapArray[0];
      };
      Heap2.prototype.pop = function() {
        var last = this.heapArray.pop();
        if (this.length > 0 && last !== void 0) {
          return this.replace(last);
        }
        return last;
      };
      Heap2.prototype.push = function() {
        var elements = [];
        for (var _i = 0; _i < arguments.length; _i++) {
          elements[_i] = arguments[_i];
        }
        if (elements.length < 1) {
          return false;
        } else if (elements.length === 1) {
          return this.add(elements[0]);
        } else {
          return this.addAll(elements);
        }
      };
      Heap2.prototype.pushpop = function(element) {
        var _a;
        if (this.compare(this.heapArray[0], element) < 0) {
          _a = __read([this.heapArray[0], element], 2), element = _a[0], this.heapArray[0] = _a[1];
          this._sortNodeDown(0);
        }
        return element;
      };
      Heap2.prototype.remove = function(o, callbackFn) {
        var _this = this;
        if (callbackFn === void 0) {
          callbackFn = Heap2.defaultIsEqual;
        }
        if (!this.heapArray.length)
          return false;
        if (o === void 0) {
          this.pop();
          return true;
        }
        var queue = [0];
        while (queue.length) {
          var idx = queue.shift();
          if (callbackFn(this.heapArray[idx], o)) {
            if (idx === 0) {
              this.pop();
            } else if (idx === this.heapArray.length - 1) {
              this.heapArray.pop();
            } else {
              this.heapArray.splice(idx, 1, this.heapArray.pop());
              this._sortNodeUp(idx);
              this._sortNodeDown(idx);
            }
            return true;
          } else if (this.compare(this.heapArray[idx], o) <= 0) {
            var children = Heap2.getChildrenIndexOf(idx).filter(function(c) {
              return c < _this.heapArray.length;
            });
            queue.push.apply(queue, __spreadArray([], __read(children), false));
          }
        }
        return false;
      };
      Heap2.prototype.replace = function(element) {
        var peek = this.heapArray[0];
        this.heapArray[0] = element;
        this._sortNodeDown(0);
        return peek;
      };
      Heap2.prototype.size = function() {
        return this.length;
      };
      Heap2.prototype.top = function(n) {
        if (n === void 0) {
          n = 1;
        }
        if (this.heapArray.length === 0 || n <= 0) {
          return [];
        } else if (this.heapArray.length === 1 || n === 1) {
          return [this.heapArray[0]];
        } else if (n >= this.heapArray.length) {
          return __spreadArray([], __read(this.heapArray), false);
        } else {
          return this._topN_push(~~n);
        }
      };
      Heap2.prototype.toArray = function() {
        return __spreadArray([], __read(this.heapArray), false);
      };
      Heap2.prototype.toString = function() {
        return this.heapArray.toString();
      };
      Heap2.prototype.get = function(i) {
        return this.heapArray[i];
      };
      Heap2.prototype.getChildrenOf = function(idx) {
        var _this = this;
        return Heap2.getChildrenIndexOf(idx).map(function(i) {
          return _this.heapArray[i];
        }).filter(function(e) {
          return e !== void 0;
        });
      };
      Heap2.prototype.getParentOf = function(idx) {
        var pi = Heap2.getParentIndexOf(idx);
        return this.heapArray[pi];
      };
      Heap2.prototype[Symbol.iterator] = function() {
        return __generator(this, function(_a) {
          switch (_a.label) {
            case 0:
              if (!this.length) return [3, 2];
              return [4, this.pop()];
            case 1:
              _a.sent();
              return [3, 0];
            case 2:
              return [
                2
                /*return*/
              ];
          }
        });
      };
      Heap2.prototype.iterator = function() {
        return this.toArray();
      };
      Heap2.prototype._applyLimit = function() {
        if (this._limit > 0 && this._limit < this.heapArray.length) {
          var rm = this.heapArray.length - this._limit;
          while (rm) {
            this.heapArray.pop();
            --rm;
          }
        }
      };
      Heap2.prototype._bottomN_push = function(n) {
        var bottomHeap = new Heap2(this.compare);
        bottomHeap.limit = n;
        bottomHeap.heapArray = this.heapArray.slice(-n);
        bottomHeap.init();
        var startAt = this.heapArray.length - 1 - n;
        var parentStartAt = Heap2.getParentIndexOf(startAt);
        var indices = [];
        for (var i = startAt; i > parentStartAt; --i) {
          indices.push(i);
        }
        var arr = this.heapArray;
        while (indices.length) {
          var i = indices.shift();
          if (this.compare(arr[i], bottomHeap.peek()) > 0) {
            bottomHeap.replace(arr[i]);
            if (i % 2) {
              indices.push(Heap2.getParentIndexOf(i));
            }
          }
        }
        return bottomHeap.toArray();
      };
      Heap2.prototype._moveNode = function(j, k) {
        var temp = this.heapArray[j];
        this.heapArray[j] = this.heapArray[k];
        this.heapArray[k] = temp;
      };
      Heap2.prototype._sortNodeDown = function(i) {
        var length = this.heapArray.length;
        var originalIndex = i;
        var value = this.heapArray[i];
        var left = 2 * i + 1;
        while (left < length) {
          var right = left + 1;
          var best = right >= length || this.compare(this.heapArray[left], this.heapArray[right]) < 0 ? left : right;
          if (this.compare(this.heapArray[best], value) < 0) {
            this.heapArray[i] = this.heapArray[best];
            i = best;
            left = 2 * i + 1;
          } else
            break;
        }
        if (i !== originalIndex) {
          this.heapArray[i] = value;
        }
      };
      Heap2.prototype._sortNodeUp = function(i) {
        var value = this.heapArray[i];
        var originalIndex = i;
        while (i > 0) {
          var pi = Heap2.getParentIndexOf(i);
          if (this.compare(value, this.heapArray[pi]) < 0) {
            this.heapArray[i] = this.heapArray[pi];
            i = pi;
          } else
            break;
        }
        if (i !== originalIndex) {
          this.heapArray[i] = value;
        }
      };
      Heap2.prototype._topN_push = function(n) {
        var topHeap = new Heap2(this._invertedCompare);
        topHeap.limit = n;
        var indices = [0];
        var arr = this.heapArray;
        while (indices.length) {
          var i = indices.shift();
          if (i < arr.length) {
            if (topHeap.length < n) {
              topHeap.push(arr[i]);
              indices.push.apply(indices, __spreadArray([], __read(Heap2.getChildrenIndexOf(i)), false));
            } else if (this.compare(arr[i], topHeap.peek()) < 0) {
              topHeap.replace(arr[i]);
              indices.push.apply(indices, __spreadArray([], __read(Heap2.getChildrenIndexOf(i)), false));
            }
          }
        }
        return topHeap.toArray();
      };
      Heap2.prototype._topN_fill = function(n) {
        var heapArray = this.heapArray;
        var topHeap = new Heap2(this._invertedCompare);
        topHeap.limit = n;
        topHeap.heapArray = heapArray.slice(0, n);
        topHeap.init();
        var branch = Heap2.getParentIndexOf(n - 1) + 1;
        var indices = [];
        for (var i = branch; i < n; ++i) {
          indices.push.apply(indices, __spreadArray([], __read(Heap2.getChildrenIndexOf(i).filter(function(l) {
            return l < heapArray.length;
          })), false));
        }
        if ((n - 1) % 2) {
          indices.push(n);
        }
        while (indices.length) {
          var i = indices.shift();
          if (i < heapArray.length) {
            if (this.compare(heapArray[i], topHeap.peek()) < 0) {
              topHeap.replace(heapArray[i]);
              indices.push.apply(indices, __spreadArray([], __read(Heap2.getChildrenIndexOf(i)), false));
            }
          }
        }
        return topHeap.toArray();
      };
      Heap2.prototype._topN_heap = function(n) {
        var topHeap = this.clone();
        var result = [];
        for (var i = 0; i < n; ++i) {
          result.push(topHeap.pop());
        }
        return result;
      };
      Heap2.prototype._topIdxOf = function(list) {
        if (!list.length) {
          return -1;
        }
        var idx = 0;
        var top = list[idx];
        for (var i = 1; i < list.length; ++i) {
          var comp = this.compare(list[i], top);
          if (comp < 0) {
            idx = i;
            top = list[i];
          }
        }
        return idx;
      };
      Heap2.prototype._topOf = function() {
        var list = [];
        for (var _i = 0; _i < arguments.length; _i++) {
          list[_i] = arguments[_i];
        }
        var heap = new Heap2(this.compare);
        heap.init(list);
        return heap.peek();
      };
      return Heap2;
    })()
  );

  // node_modules/@mcap/core/dist/esm/CachedReadable.js
  var _readable, _cache, _maxCacheSizeBytes, _currentCacheSizeBytes, _size;
  var CachedReadable = class {
    constructor(readable, maxCacheSizeBytes) {
      /**
       * The underlying source of the data to be cached.
       */
      __privateAdd(this, _readable);
      /**
       * Cached data. Indexed by offset request and stored as a Uint8Array.
       * If the requested size is less than the cached data, the cached data is returned as a subarray.
       * If the requested size is greater than the cached data, the a new request is made to the underlying readable.
       */
      __privateAdd(this, _cache, /* @__PURE__ */ new Map());
      /**
       * The maximum size of the cache in bytes.
       */
      __privateAdd(this, _maxCacheSizeBytes);
      /**
       * The current size of the cache in bytes.
       */
      __privateAdd(this, _currentCacheSizeBytes, 0);
      /**
       * The size of the underlying readable.
       */
      __privateAdd(this, _size);
      __privateSet(this, _readable, readable);
      __privateSet(this, _maxCacheSizeBytes, maxCacheSizeBytes);
    }
    async size() {
      if (__privateGet(this, _size) == void 0) {
        __privateSet(this, _size, await __privateGet(this, _readable).size());
      }
      return __privateGet(this, _size);
    }
    async read(offset, size) {
      const requestedSize = Number(size);
      const cached = __privateGet(this, _cache).get(offset);
      if (cached != void 0 && cached.byteLength >= requestedSize) {
        return cached.byteLength === requestedSize ? cached : cached.subarray(0, requestedSize);
      }
      const data = await __privateGet(this, _readable).read(offset, size);
      if (__privateGet(this, _currentCacheSizeBytes) + data.byteLength <= __privateGet(this, _maxCacheSizeBytes)) {
        const copy = new Uint8Array(data);
        __privateGet(this, _cache).set(offset, copy);
        __privateSet(this, _currentCacheSizeBytes, __privateGet(this, _currentCacheSizeBytes) + copy.byteLength);
        return copy;
      }
      return data;
    }
  };
  _readable = new WeakMap();
  _cache = new WeakMap();
  _maxCacheSizeBytes = new WeakMap();
  _currentCacheSizeBytes = new WeakMap();
  _size = new WeakMap();

  // node_modules/@mcap/core/dist/esm/getBigUint64.js
  var getBigUint64 = typeof DataView.prototype.getBigUint64 === "function" ? DataView.prototype.getBigUint64 : function(offset, littleEndian) {
    const lo = littleEndian === true ? this.getUint32(offset, littleEndian) : this.getUint32(offset + 4, littleEndian);
    const hi = littleEndian === true ? this.getUint32(offset + 4, littleEndian) : this.getUint32(offset, littleEndian);
    return BigInt(hi) << 32n | BigInt(lo);
  };

  // node_modules/@mcap/core/dist/esm/Reader.js
  var textDecoder = new TextDecoder();
  var _view, _viewU8;
  var Reader = class {
    constructor(view, offset = 0) {
      __privateAdd(this, _view);
      __privateAdd(this, _viewU8);
      __publicField(this, "offset");
      __privateSet(this, _view, view);
      __privateSet(this, _viewU8, new Uint8Array(view.buffer, view.byteOffset, view.byteLength));
      this.offset = offset;
    }
    // Should be ~identical to the constructor, it allows us to reinitialize the reader when
    // the view changes,  without creating a new instance, avoiding allocation / GC overhead
    reset(view, offset = 0) {
      __privateSet(this, _view, view);
      __privateSet(this, _viewU8, new Uint8Array(view.buffer, view.byteOffset, view.byteLength));
      this.offset = offset;
    }
    bytesRemaining() {
      return __privateGet(this, _viewU8).length - this.offset;
    }
    uint8() {
      const value = __privateGet(this, _view).getUint8(this.offset);
      this.offset += 1;
      return value;
    }
    uint16() {
      const value = __privateGet(this, _view).getUint16(this.offset, true);
      this.offset += 2;
      return value;
    }
    uint32() {
      const value = __privateGet(this, _view).getUint32(this.offset, true);
      this.offset += 4;
      return value;
    }
    uint64() {
      const value = getBigUint64.call(__privateGet(this, _view), this.offset, true);
      this.offset += 8;
      return value;
    }
    string() {
      const length = this.uint32();
      if (length === 0) {
        return "";
      } else if (length > this.bytesRemaining()) {
        throw new Error(`String length ${length} exceeds bounds of buffer`);
      }
      return textDecoder.decode(this.u8ArrayBorrow(length));
    }
    keyValuePairs(readKey, readValue) {
      const length = this.uint32();
      if (this.offset + length > __privateGet(this, _view).byteLength) {
        throw new Error(`Key-value pairs length ${length} exceeds bounds of buffer`);
      }
      const result = [];
      const endOffset = this.offset + length;
      try {
        while (this.offset < endOffset) {
          result.push([readKey(this), readValue(this)]);
        }
      } catch (err) {
        throw new Error(`Error reading key-value pairs: ${err.message}`);
      }
      if (this.offset !== endOffset) {
        throw new Error(`Key-value pairs length (${this.offset - endOffset + length}) greater than expected (${length})`);
      }
      return result;
    }
    map(readKey, readValue) {
      const length = this.uint32();
      if (this.offset + length > __privateGet(this, _view).byteLength) {
        throw new Error(`Map length ${length} exceeds bounds of buffer`);
      }
      const result = /* @__PURE__ */ new Map();
      const endOffset = this.offset + length;
      try {
        while (this.offset < endOffset) {
          const key = readKey(this);
          const value = readValue(this);
          const existingValue = result.get(key);
          if (existingValue != void 0) {
            throw new Error(`Duplicate key ${String(key)} (${String(existingValue)} vs ${String(value)})`);
          }
          result.set(key, value);
        }
      } catch (err) {
        throw new Error(`Error reading map: ${err.message}`);
      }
      if (this.offset !== endOffset) {
        throw new Error(`Map length (${this.offset - endOffset + length}) greater than expected (${length})`);
      }
      return result;
    }
    // Read a borrowed Uint8Array, useful temp references or borrow semantics
    u8ArrayBorrow(length) {
      const result = __privateGet(this, _viewU8).subarray(this.offset, this.offset + length);
      this.offset += length;
      return result;
    }
    // Read a copied Uint8Array from the underlying buffer, use when you need to keep the data around
    u8ArrayCopy(length) {
      const result = __privateGet(this, _viewU8).slice(this.offset, this.offset + length);
      this.offset += length;
      return result;
    }
  };
  _view = new WeakMap();
  _viewU8 = new WeakMap();

  // node_modules/@mcap/core/dist/esm/constants.js
  var MCAP_MAGIC = Object.freeze([137, 77, 67, 65, 80, 48, 13, 10]);
  var Opcode;
  (function(Opcode2) {
    Opcode2[Opcode2["MIN"] = 1] = "MIN";
    Opcode2[Opcode2["HEADER"] = 1] = "HEADER";
    Opcode2[Opcode2["FOOTER"] = 2] = "FOOTER";
    Opcode2[Opcode2["SCHEMA"] = 3] = "SCHEMA";
    Opcode2[Opcode2["CHANNEL"] = 4] = "CHANNEL";
    Opcode2[Opcode2["MESSAGE"] = 5] = "MESSAGE";
    Opcode2[Opcode2["CHUNK"] = 6] = "CHUNK";
    Opcode2[Opcode2["MESSAGE_INDEX"] = 7] = "MESSAGE_INDEX";
    Opcode2[Opcode2["CHUNK_INDEX"] = 8] = "CHUNK_INDEX";
    Opcode2[Opcode2["ATTACHMENT"] = 9] = "ATTACHMENT";
    Opcode2[Opcode2["ATTACHMENT_INDEX"] = 10] = "ATTACHMENT_INDEX";
    Opcode2[Opcode2["STATISTICS"] = 11] = "STATISTICS";
    Opcode2[Opcode2["METADATA"] = 12] = "METADATA";
    Opcode2[Opcode2["METADATA_INDEX"] = 13] = "METADATA_INDEX";
    Opcode2[Opcode2["SUMMARY_OFFSET"] = 14] = "SUMMARY_OFFSET";
    Opcode2[Opcode2["DATA_END"] = 15] = "DATA_END";
    Opcode2[Opcode2["MAX"] = 15] = "MAX";
  })(Opcode || (Opcode = {}));

  // node_modules/@mcap/core/dist/esm/parse.js
  function parseMagic(reader) {
    if (reader.bytesRemaining() < MCAP_MAGIC.length) {
      return void 0;
    }
    const magic = reader.u8ArrayBorrow(MCAP_MAGIC.length);
    if (!MCAP_MAGIC.every((val, i) => val === magic[i])) {
      throw new Error(`Expected MCAP magic '${MCAP_MAGIC.map((val) => val.toString(16).padStart(2, "0")).join(" ")}', found '${Array.from(magic, (_, i) => magic[i].toString(16).padStart(2, "0")).join(" ")}'`);
    }
    return { specVersion: "0" };
  }
  function parseRecord(reader, validateCrcs = false) {
    const RECORD_HEADER_SIZE = 1 + 8;
    if (reader.bytesRemaining() < RECORD_HEADER_SIZE) {
      return void 0;
    }
    const start = reader.offset;
    const opcode = reader.uint8();
    const recordLength = reader.uint64();
    if (recordLength > Number.MAX_SAFE_INTEGER) {
      throw new Error(`Record content length ${recordLength} is too large`);
    }
    const recordLengthNum = Number(recordLength);
    if (reader.bytesRemaining() < recordLengthNum) {
      reader.offset = start;
      return void 0;
    }
    let result;
    switch (opcode) {
      case Opcode.HEADER:
        result = parseHeader(reader, recordLengthNum);
        break;
      case Opcode.FOOTER:
        result = parseFooter(reader, recordLengthNum);
        break;
      case Opcode.SCHEMA:
        result = parseSchema(reader, recordLengthNum);
        break;
      case Opcode.CHANNEL:
        result = parseChannel(reader, recordLengthNum);
        break;
      case Opcode.MESSAGE:
        result = parseMessage(reader, recordLengthNum);
        break;
      case Opcode.CHUNK:
        result = parseChunk(reader, recordLengthNum);
        break;
      case Opcode.MESSAGE_INDEX:
        result = parseMessageIndex(reader, recordLengthNum);
        break;
      case Opcode.CHUNK_INDEX:
        result = parseChunkIndex(reader, recordLengthNum);
        break;
      case Opcode.ATTACHMENT:
        result = parseAttachment(reader, recordLengthNum, validateCrcs);
        break;
      case Opcode.ATTACHMENT_INDEX:
        result = parseAttachmentIndex(reader, recordLengthNum);
        break;
      case Opcode.STATISTICS:
        result = parseStatistics(reader, recordLengthNum);
        break;
      case Opcode.METADATA:
        result = parseMetadata(reader, recordLengthNum);
        break;
      case Opcode.METADATA_INDEX:
        result = parseMetadataIndex(reader, recordLengthNum);
        break;
      case Opcode.SUMMARY_OFFSET:
        result = parseSummaryOffset(reader, recordLengthNum);
        break;
      case Opcode.DATA_END:
        result = parseDataEnd(reader, recordLengthNum);
        break;
      default:
        result = parseUnknown(reader, recordLengthNum, opcode);
        break;
    }
    reader.offset = start + RECORD_HEADER_SIZE + recordLengthNum;
    return result;
  }
  function parseUnknown(reader, recordLength, opcode) {
    const data = reader.u8ArrayBorrow(recordLength);
    return {
      type: "Unknown",
      opcode,
      data
    };
  }
  function parseHeader(reader, recordLength) {
    const startOffset = reader.offset;
    const profile = reader.string();
    const library = reader.string();
    reader.offset = startOffset + recordLength;
    return { type: "Header", profile, library };
  }
  function parseFooter(reader, recordLength) {
    const startOffset = reader.offset;
    const summaryStart = reader.uint64();
    const summaryOffsetStart = reader.uint64();
    const summaryCrc = reader.uint32();
    reader.offset = startOffset + recordLength;
    return {
      type: "Footer",
      summaryStart,
      summaryOffsetStart,
      summaryCrc
    };
  }
  function parseSchema(reader, recordLength) {
    const start = reader.offset;
    const id = reader.uint16();
    const name = reader.string();
    const encoding = reader.string();
    const dataLen = reader.uint32();
    const end = reader.offset;
    if (recordLength - (end - start) < dataLen) {
      throw new Error(`Schema data length ${dataLen} exceeds bounds of record`);
    }
    const data = reader.u8ArrayCopy(dataLen);
    reader.offset = start + recordLength;
    return {
      type: "Schema",
      id,
      encoding,
      name,
      data
    };
  }
  function parseChannel(reader, recordLength) {
    const startOffset = reader.offset;
    const channelId = reader.uint16();
    const schemaId = reader.uint16();
    const topicName = reader.string();
    const messageEncoding = reader.string();
    const metadata = reader.map((r) => r.string(), (r) => r.string());
    reader.offset = startOffset + recordLength;
    return {
      type: "Channel",
      id: channelId,
      schemaId,
      topic: topicName,
      messageEncoding,
      metadata
    };
  }
  function parseMessage(reader, recordLength) {
    const MESSAGE_PREFIX_SIZE = 2 + 4 + 8 + 8;
    const channelId = reader.uint16();
    const sequence = reader.uint32();
    const logTime = reader.uint64();
    const publishTime = reader.uint64();
    const data = reader.u8ArrayCopy(recordLength - MESSAGE_PREFIX_SIZE);
    return {
      type: "Message",
      channelId,
      sequence,
      logTime,
      publishTime,
      data
    };
  }
  function parseChunk(reader, recordLength) {
    const start = reader.offset;
    const startTime = reader.uint64();
    const endTime = reader.uint64();
    const uncompressedSize = reader.uint64();
    const uncompressedCrc = reader.uint32();
    const compression = reader.string();
    const recordsByteLength = Number(reader.uint64());
    const end = reader.offset;
    const prefixSize = end - start;
    if (recordsByteLength + prefixSize > recordLength) {
      throw new Error("Chunk records length exceeds remaining record size");
    }
    const records = reader.u8ArrayCopy(recordsByteLength);
    reader.offset = start + recordLength;
    return {
      type: "Chunk",
      messageStartTime: startTime,
      messageEndTime: endTime,
      compression,
      uncompressedSize,
      uncompressedCrc,
      records
    };
  }
  function parseMessageIndex(reader, recordLength) {
    const startOffset = reader.offset;
    const channelId = reader.uint16();
    const records = reader.keyValuePairs((r) => r.uint64(), (r) => r.uint64());
    reader.offset = startOffset + recordLength;
    return {
      type: "MessageIndex",
      channelId,
      records
    };
  }
  function parseChunkIndex(reader, recordLength) {
    const startOffset = reader.offset;
    const messageStartTime = reader.uint64();
    const messageEndTime = reader.uint64();
    const chunkStartOffset = reader.uint64();
    const chunkLength = reader.uint64();
    const messageIndexOffsets = reader.map((r) => r.uint16(), (r) => r.uint64());
    const messageIndexLength = reader.uint64();
    const compression = reader.string();
    const compressedSize = reader.uint64();
    const uncompressedSize = reader.uint64();
    reader.offset = startOffset + recordLength;
    return {
      type: "ChunkIndex",
      messageStartTime,
      messageEndTime,
      chunkStartOffset,
      chunkLength,
      messageIndexOffsets,
      messageIndexLength,
      compression,
      compressedSize,
      uncompressedSize
    };
  }
  function parseAttachment(reader, recordLength, validateCrcs) {
    const startOffset = reader.offset;
    const logTime = reader.uint64();
    const createTime = reader.uint64();
    const name = reader.string();
    const mediaType = reader.string();
    const dataLen = reader.uint64();
    if (BigInt(reader.offset) + dataLen > Number.MAX_SAFE_INTEGER) {
      throw new Error(`Attachment too large: ${dataLen}`);
    }
    if (reader.offset + Number(dataLen) + 4 > startOffset + recordLength) {
      throw new Error(`Attachment data length ${dataLen} exceeds bounds of record`);
    }
    const data = reader.u8ArrayCopy(Number(dataLen));
    const crcLength = reader.offset - startOffset;
    const expectedCrc = reader.uint32();
    if (validateCrcs && expectedCrc !== 0) {
      reader.offset = startOffset;
      const fullData = reader.u8ArrayBorrow(crcLength);
      const actualCrc = crc32(fullData);
      reader.offset = startOffset + crcLength + 4;
      if (actualCrc !== expectedCrc) {
        throw new Error(`Attachment CRC32 mismatch: expected ${expectedCrc}, actual ${actualCrc}`);
      }
    }
    reader.offset = startOffset + recordLength;
    return {
      type: "Attachment",
      logTime,
      createTime,
      name,
      mediaType,
      data
    };
  }
  function parseAttachmentIndex(reader, recordLength) {
    const startOffset = reader.offset;
    const offset = reader.uint64();
    const length = reader.uint64();
    const logTime = reader.uint64();
    const createTime = reader.uint64();
    const dataSize = reader.uint64();
    const name = reader.string();
    const mediaType = reader.string();
    reader.offset = startOffset + recordLength;
    return {
      type: "AttachmentIndex",
      offset,
      length,
      logTime,
      createTime,
      dataSize,
      name,
      mediaType
    };
  }
  function parseStatistics(reader, recordLength) {
    const startOffset = reader.offset;
    const messageCount = reader.uint64();
    const schemaCount = reader.uint16();
    const channelCount = reader.uint32();
    const attachmentCount = reader.uint32();
    const metadataCount = reader.uint32();
    const chunkCount = reader.uint32();
    const messageStartTime = reader.uint64();
    const messageEndTime = reader.uint64();
    const channelMessageCounts = reader.map((r) => r.uint16(), (r) => r.uint64());
    reader.offset = startOffset + recordLength;
    return {
      type: "Statistics",
      messageCount,
      schemaCount,
      channelCount,
      attachmentCount,
      metadataCount,
      chunkCount,
      messageStartTime,
      messageEndTime,
      channelMessageCounts
    };
  }
  function parseMetadata(reader, recordLength) {
    const startOffset = reader.offset;
    const name = reader.string();
    const metadata = reader.map((r) => r.string(), (r) => r.string());
    reader.offset = startOffset + recordLength;
    return { type: "Metadata", metadata, name };
  }
  function parseMetadataIndex(reader, recordLength) {
    const startOffset = reader.offset;
    const offset = reader.uint64();
    const length = reader.uint64();
    const name = reader.string();
    reader.offset = startOffset + recordLength;
    return {
      type: "MetadataIndex",
      offset,
      length,
      name
    };
  }
  function parseSummaryOffset(reader, recordLength) {
    const startOffset = reader.offset;
    const groupOpcode = reader.uint8();
    const groupStart = reader.uint64();
    const groupLength = reader.uint64();
    reader.offset = startOffset + recordLength;
    return {
      type: "SummaryOffset",
      groupOpcode,
      groupStart,
      groupLength
    };
  }
  function parseDataEnd(reader, recordLength) {
    const startOffset = reader.offset;
    const dataSectionCrc = reader.uint32();
    reader.offset = startOffset + recordLength;
    return {
      type: "DataEnd",
      dataSectionCrc
    };
  }

  // node_modules/@mcap/core/dist/esm/sortedIndexBy.js
  function sortedIndexBy(array, value, iteratee) {
    let low = 0;
    let high = array.length;
    if (high === 0) {
      return 0;
    }
    const computedValue = iteratee(value);
    while (low < high) {
      const mid = low + high >>> 1;
      const curComputedValue = iteratee(array[mid][0]);
      if (curComputedValue < computedValue) {
        low = mid + 1;
      } else {
        high = mid;
      }
    }
    return high;
  }

  // node_modules/@mcap/core/dist/esm/sortedLastIndex.js
  function sortedLastIndexBy(array, value, iteratee) {
    let low = 0;
    let high = array.length;
    if (high === 0) {
      return 0;
    }
    const computedValue = iteratee(value);
    while (low < high) {
      const mid = low + high >>> 1;
      const computed = iteratee(array[mid][0]);
      if (computed <= computedValue) {
        low = mid + 1;
      } else {
        high = mid;
      }
    }
    return high;
  }

  // node_modules/@mcap/core/dist/esm/ChunkCursor.js
  var _relevantChannels, _startTime, _endTime, _reverse, _readFullMessageIndexRange, _orderedMessageOffsets, _nextMessageOffsetIndex, _ChunkCursor_instances, getSortTime_fn;
  var ChunkCursor = class {
    constructor(params) {
      __privateAdd(this, _ChunkCursor_instances);
      __publicField(this, "chunkIndex");
      __privateAdd(this, _relevantChannels);
      __privateAdd(this, _startTime);
      __privateAdd(this, _endTime);
      __privateAdd(this, _reverse);
      __privateAdd(this, _readFullMessageIndexRange);
      // List of message offsets (across all channels) sorted by logTime.
      __privateAdd(this, _orderedMessageOffsets);
      // Index for the next message offset. Gets incremented for every popMessage() call.
      __privateAdd(this, _nextMessageOffsetIndex, 0);
      this.chunkIndex = params.chunkIndex;
      __privateSet(this, _relevantChannels, params.relevantChannels);
      __privateSet(this, _startTime, params.startTime);
      __privateSet(this, _endTime, params.endTime);
      __privateSet(this, _reverse, params.reverse);
      __privateSet(this, _readFullMessageIndexRange, params.readFullMessageIndexRange ?? false);
      if (this.chunkIndex.messageIndexLength === 0n) {
        if (this.chunkIndex.messageStartTime !== 0n || this.chunkIndex.messageEndTime !== 0n) {
          throw new Error(`Encountered a chunk index without message indexes and non-zero start and end times`);
        }
      }
    }
    /**
     * Returns `< 0` if the callee's next available message logTime is earlier than `other`'s, `> 0`
     * for the opposite case. Never returns `0` because ties are broken by the chunks' offsets in the
     * file.
     *
     * Cursors that still need `loadMessageIndexes()` are sorted earlier so the caller can load them
     * and re-sort the cursors.
     */
    compare(other) {
      var _a;
      if (__privateGet(this, _reverse) !== __privateGet(other, _reverse)) {
        throw new Error("Cannot compare a reversed ChunkCursor to a non-reversed ChunkCursor");
      }
      let diff = Number(__privateMethod(this, _ChunkCursor_instances, getSortTime_fn).call(this) - __privateMethod(_a = other, _ChunkCursor_instances, getSortTime_fn).call(_a));
      if (diff === 0) {
        diff = Number(this.chunkIndex.chunkStartOffset - other.chunkIndex.chunkStartOffset);
      }
      return __privateGet(this, _reverse) ? -diff : diff;
    }
    /**
     * Returns true if there are more messages available in the chunk. Message indexes must have been
     * loaded before using this method.
     */
    hasMoreMessages() {
      if (__privateGet(this, _orderedMessageOffsets) == void 0) {
        throw new Error("loadMessageIndexes() must be called before hasMore()");
      }
      return __privateGet(this, _nextMessageOffsetIndex) < __privateGet(this, _orderedMessageOffsets).length;
    }
    /**
     * Pop a message offset off of the chunk cursor. Message indexes must have been loaded before
     * using this method.
     */
    popMessage() {
      if (__privateGet(this, _orderedMessageOffsets) == void 0) {
        throw new Error("loadMessageIndexes() must be called before popMessage()");
      }
      if (__privateGet(this, _nextMessageOffsetIndex) >= __privateGet(this, _orderedMessageOffsets).length) {
        throw new Error(`Unexpected popMessage() call when no more messages are available, in chunk at offset ${this.chunkIndex.chunkStartOffset}`);
      }
      return __privateGet(this, _orderedMessageOffsets)[__privateWrapper(this, _nextMessageOffsetIndex)._++];
    }
    /**
     * Returns true if message indexes have been loaded, false if `loadMessageIndexes()` needs to be
     * called.
     */
    hasMessageIndexes() {
      return __privateGet(this, _orderedMessageOffsets) != void 0;
    }
    async loadMessageIndexes(readable) {
      const reverse = __privateGet(this, _reverse);
      let messageIndexStartOffset;
      let relevantMessageIndexStartOffset;
      const readFullRange = __privateGet(this, _readFullMessageIndexRange);
      for (const [channelId, offset] of this.chunkIndex.messageIndexOffsets) {
        if (messageIndexStartOffset == void 0 || offset < messageIndexStartOffset) {
          messageIndexStartOffset = offset;
        }
        if (readFullRange || !__privateGet(this, _relevantChannels) || __privateGet(this, _relevantChannels).has(channelId)) {
          if (relevantMessageIndexStartOffset == void 0 || offset < relevantMessageIndexStartOffset) {
            relevantMessageIndexStartOffset = offset;
          }
        }
      }
      if (messageIndexStartOffset == void 0 || relevantMessageIndexStartOffset == void 0) {
        __privateSet(this, _orderedMessageOffsets, []);
        return;
      }
      const messageIndexEndOffset = messageIndexStartOffset + this.chunkIndex.messageIndexLength;
      const messageIndexes = await readable.read(relevantMessageIndexStartOffset, messageIndexEndOffset - relevantMessageIndexStartOffset);
      const messageIndexesView = new DataView(messageIndexes.buffer, messageIndexes.byteOffset, messageIndexes.byteLength);
      const reader = new Reader(messageIndexesView);
      const arrayOfMessageOffsets = [];
      let record;
      while (record = parseRecord(reader, true)) {
        if (record.type !== "MessageIndex") {
          continue;
        }
        if (record.records.length === 0 || __privateGet(this, _relevantChannels) && !__privateGet(this, _relevantChannels).has(record.channelId)) {
          continue;
        }
        arrayOfMessageOffsets.push(record.records);
      }
      if (reader.bytesRemaining() !== 0) {
        throw new Error(`${reader.bytesRemaining()} bytes remaining in message index section`);
      }
      __privateSet(this, _orderedMessageOffsets, arrayOfMessageOffsets.flat().sort(([logTimeA, offsetA], [logTimeB, offsetB]) => {
        let diff = Number(logTimeA - logTimeB);
        if (diff === 0) {
          diff = Number(offsetA - offsetB);
        }
        return diff;
      }));
      if (reverse) {
        __privateGet(this, _orderedMessageOffsets).reverse();
      }
      if (__privateGet(this, _orderedMessageOffsets).length === 0) {
        return;
      }
      const [logTimeFirstMessage] = __privateGet(this, _orderedMessageOffsets)[0];
      if (logTimeFirstMessage < this.chunkIndex.messageStartTime) {
        throw new Error(`Chunk at offset ${this.chunkIndex.chunkStartOffset} contains a message with logTime (${logTimeFirstMessage}) earlier than chunk messageStartTime (${this.chunkIndex.messageStartTime})`);
      }
      const [logTimeLastMessage] = __privateGet(this, _orderedMessageOffsets)[__privateGet(this, _orderedMessageOffsets).length - 1];
      if (logTimeLastMessage > this.chunkIndex.messageEndTime) {
        throw new Error(`Chunk at offset ${this.chunkIndex.chunkStartOffset} contains a message with logTime (${logTimeLastMessage}) later than chunk messageEndTime (${this.chunkIndex.messageEndTime})`);
      }
      const startTime = reverse ? __privateGet(this, _endTime) : __privateGet(this, _startTime);
      const endTime = reverse ? __privateGet(this, _startTime) : __privateGet(this, _endTime);
      const iteratee = reverse ? (logTime) => -logTime : (logTime) => logTime;
      let startIndex;
      let endIndex;
      if (startTime != void 0) {
        startIndex = sortedIndexBy(__privateGet(this, _orderedMessageOffsets), startTime, iteratee);
      }
      if (endTime != void 0) {
        endIndex = sortedLastIndexBy(__privateGet(this, _orderedMessageOffsets), endTime, iteratee);
      }
      if (startIndex != void 0 || endIndex != void 0) {
        __privateSet(this, _orderedMessageOffsets, __privateGet(this, _orderedMessageOffsets).slice(startIndex, endIndex));
      }
    }
  };
  _relevantChannels = new WeakMap();
  _startTime = new WeakMap();
  _endTime = new WeakMap();
  _reverse = new WeakMap();
  _readFullMessageIndexRange = new WeakMap();
  _orderedMessageOffsets = new WeakMap();
  _nextMessageOffsetIndex = new WeakMap();
  _ChunkCursor_instances = new WeakSet();
  // Get the next available message logTime which is being used when comparing chunkCursors (for ordering purposes).
  getSortTime_fn = function() {
    if (__privateGet(this, _orderedMessageOffsets) != void 0 && __privateGet(this, _orderedMessageOffsets).length > 0 && __privateGet(this, _nextMessageOffsetIndex) < __privateGet(this, _orderedMessageOffsets).length) {
      return __privateGet(this, _orderedMessageOffsets)[__privateGet(this, _nextMessageOffsetIndex)][0];
    }
    return __privateGet(this, _reverse) ? this.chunkIndex.messageEndTime : this.chunkIndex.messageStartTime;
  };

  // node_modules/@mcap/core/dist/esm/McapIndexedReader.js
  var _readable2, _messageIndexReadable, _decompressHandlers, _messageStartTime, _messageEndTime, _attachmentStartTime, _attachmentEndTime, _McapIndexedReader_instances, errorWithLibrary_fn, loadChunkData_fn;
  var _McapIndexedReader = class _McapIndexedReader {
    constructor(args) {
      __privateAdd(this, _McapIndexedReader_instances);
      __publicField(this, "chunkIndexes");
      __publicField(this, "attachmentIndexes");
      __publicField(this, "metadataIndexes", []);
      __publicField(this, "channelsById");
      __publicField(this, "schemasById");
      __publicField(this, "statistics");
      __publicField(this, "summaryOffsetsByOpcode");
      __publicField(this, "header");
      __publicField(this, "footer");
      // Used for appending attachments/metadata to existing MCAP files
      __publicField(this, "dataEndOffset");
      __publicField(this, "dataSectionCrc");
      __privateAdd(this, _readable2);
      __privateAdd(this, _messageIndexReadable);
      __privateAdd(this, _decompressHandlers);
      __privateAdd(this, _messageStartTime);
      __privateAdd(this, _messageEndTime);
      __privateAdd(this, _attachmentStartTime);
      __privateAdd(this, _attachmentEndTime);
      __privateSet(this, _readable2, args.readable);
      this.chunkIndexes = args.chunkIndexes;
      this.attachmentIndexes = args.attachmentIndexes;
      this.metadataIndexes = args.metadataIndexes;
      this.statistics = args.statistics;
      __privateSet(this, _decompressHandlers, args.decompressHandlers);
      this.channelsById = args.channelsById;
      this.schemasById = args.schemasById;
      this.summaryOffsetsByOpcode = args.summaryOffsetsByOpcode;
      this.header = args.header;
      this.footer = args.footer;
      this.dataEndOffset = args.dataEndOffset;
      this.dataSectionCrc = args.dataSectionCrc;
      const messageIndexCacheSizeBytes = args.messageIndexCacheSizeBytes ?? 0;
      __privateSet(this, _messageIndexReadable, messageIndexCacheSizeBytes > 0 ? new CachedReadable(__privateGet(this, _readable2), messageIndexCacheSizeBytes) : __privateGet(this, _readable2));
      for (const chunk of args.chunkIndexes) {
        if (__privateGet(this, _messageStartTime) == void 0 || chunk.messageStartTime < __privateGet(this, _messageStartTime)) {
          __privateSet(this, _messageStartTime, chunk.messageStartTime);
        }
        if (__privateGet(this, _messageEndTime) == void 0 || chunk.messageEndTime > __privateGet(this, _messageEndTime)) {
          __privateSet(this, _messageEndTime, chunk.messageEndTime);
        }
      }
      for (const attachment of args.attachmentIndexes) {
        if (__privateGet(this, _attachmentStartTime) == void 0 || attachment.logTime < __privateGet(this, _attachmentStartTime)) {
          __privateSet(this, _attachmentStartTime, attachment.logTime);
        }
        if (__privateGet(this, _attachmentEndTime) == void 0 || attachment.logTime > __privateGet(this, _attachmentEndTime)) {
          __privateSet(this, _attachmentEndTime, attachment.logTime);
        }
      }
    }
    static async Initialize({ readable, decompressHandlers, messageIndexCacheSizeBytes }) {
      const size = await readable.size();
      let header;
      let headerEndOffset;
      {
        const headerPrefix = await readable.read(0n, BigInt(MCAP_MAGIC.length + /* Opcode.HEADER */
        1 + /* record content length */
        8));
        const headerPrefixView = new DataView(headerPrefix.buffer, headerPrefix.byteOffset, headerPrefix.byteLength);
        void parseMagic(new Reader(headerPrefixView));
        const headerContentLength = headerPrefixView.getBigUint64(MCAP_MAGIC.length + /* Opcode.HEADER */
        1, true);
        const headerReadLength = (
          /* Opcode.HEADER */
          1n + /* record content length */
          8n + headerContentLength
        );
        const headerRecord = await readable.read(BigInt(MCAP_MAGIC.length), headerReadLength);
        headerEndOffset = BigInt(MCAP_MAGIC.length) + headerReadLength;
        const headerReader = new Reader(new DataView(headerRecord.buffer, headerRecord.byteOffset, headerRecord.byteLength));
        const headerResult = parseRecord(headerReader, true);
        if (headerResult?.type !== "Header") {
          throw new Error(`Unable to read header at beginning of file; found ${headerResult?.type ?? "nothing"}`);
        }
        if (headerReader.bytesRemaining() !== 0) {
          throw new Error(`${headerReader.bytesRemaining()} bytes remaining after parsing header`);
        }
        header = headerResult;
      }
      function errorWithLibrary(message) {
        return new Error(`${message} [library=${header.library}]`);
      }
      let footerOffset;
      let footerAndMagicView;
      {
        const headerLengthLowerBound = BigInt(MCAP_MAGIC.length + /* Opcode.HEADER */
        1 + /* record content length */
        8 + /* profile length */
        4 + /* library length */
        4);
        const footerAndMagicReadLength = BigInt(
          /* Opcode.FOOTER */
          1 + /* record content length */
          8 + /* summaryStart */
          8 + /* summaryOffsetStart */
          8 + /* crc */
          4 + MCAP_MAGIC.length
        );
        if (size < headerLengthLowerBound + footerAndMagicReadLength) {
          throw errorWithLibrary(`File size (${size}) is too small to be valid MCAP`);
        }
        footerOffset = size - footerAndMagicReadLength;
        const footerBuffer = await readable.read(footerOffset, footerAndMagicReadLength);
        footerAndMagicView = new DataView(footerBuffer.buffer, footerBuffer.byteOffset, footerBuffer.byteLength);
      }
      try {
        void parseMagic(new Reader(footerAndMagicView, footerAndMagicView.byteLength - MCAP_MAGIC.length));
      } catch (error) {
        throw errorWithLibrary(error.message);
      }
      let footer;
      {
        const footerReader = new Reader(footerAndMagicView);
        const footerRecord = parseRecord(footerReader, true);
        if (footerRecord?.type !== "Footer") {
          throw errorWithLibrary(`Unable to read footer from end of file (offset ${footerOffset}); found ${footerRecord?.type ?? "nothing"}`);
        }
        if (footerReader.bytesRemaining() !== MCAP_MAGIC.length) {
          throw errorWithLibrary(`${footerReader.bytesRemaining() - MCAP_MAGIC.length} bytes remaining after parsing footer`);
        }
        footer = footerRecord;
      }
      if (footer.summaryStart === 0n) {
        throw errorWithLibrary("File is not indexed");
      }
      const footerPrefix = new Uint8Array(
        /* Opcode.FOOTER */
        1 + /* record content length */
        8 + /* summary start */
        8 + /* summary offset start */
        8
      );
      footerPrefix.set(new Uint8Array(footerAndMagicView.buffer, footerAndMagicView.byteOffset, footerPrefix.byteLength));
      const dataEndLength = (
        /* Opcode.DATA_END */
        1n + /* record content length */
        8n + /* data_section_crc */
        4n
      );
      const dataEndOffset = footer.summaryStart - dataEndLength;
      if (dataEndOffset < headerEndOffset) {
        throw errorWithLibrary(`Expected DataEnd position (summary start ${footer.summaryStart} - ${dataEndLength} = ${dataEndOffset}) to be after Header end offset (${headerEndOffset})`);
      }
      const dataEndAndSummarySection = await readable.read(dataEndOffset, footerOffset - dataEndOffset);
      if (footer.summaryCrc !== 0) {
        let summaryCrc = crc32Init();
        summaryCrc = crc32Update(summaryCrc, dataEndAndSummarySection.subarray(Number(dataEndLength)));
        summaryCrc = crc32Update(summaryCrc, footerPrefix);
        summaryCrc = crc32Final(summaryCrc);
        if (summaryCrc !== footer.summaryCrc) {
          throw errorWithLibrary(`Incorrect summary CRC ${summaryCrc} (expected ${footer.summaryCrc})`);
        }
      }
      const indexView = new DataView(dataEndAndSummarySection.buffer, dataEndAndSummarySection.byteOffset, dataEndAndSummarySection.byteLength);
      const indexReader = new Reader(indexView);
      const channelsById = /* @__PURE__ */ new Map();
      const schemasById = /* @__PURE__ */ new Map();
      const chunkIndexes = [];
      const attachmentIndexes = [];
      const metadataIndexes = [];
      const summaryOffsetsByOpcode = /* @__PURE__ */ new Map();
      let statistics;
      let dataSectionCrc;
      let first = true;
      let result;
      while (result = parseRecord(indexReader, true)) {
        if (first && result.type !== "DataEnd") {
          throw errorWithLibrary(`Expected DataEnd record to precede summary section, but found ${result.type}`);
        }
        first = false;
        switch (result.type) {
          case "Schema":
            schemasById.set(result.id, result);
            break;
          case "Channel":
            channelsById.set(result.id, result);
            break;
          case "ChunkIndex":
            chunkIndexes.push(result);
            break;
          case "AttachmentIndex":
            attachmentIndexes.push(result);
            break;
          case "MetadataIndex":
            metadataIndexes.push(result);
            break;
          case "Statistics":
            if (statistics) {
              throw errorWithLibrary("Duplicate Statistics record");
            }
            statistics = result;
            break;
          case "SummaryOffset":
            summaryOffsetsByOpcode.set(result.groupOpcode, result);
            break;
          case "DataEnd":
            dataSectionCrc = result.dataSectionCrc === 0 ? void 0 : result.dataSectionCrc;
            break;
          case "Header":
          case "Footer":
          case "Message":
          case "Chunk":
          case "MessageIndex":
          case "Attachment":
          case "Metadata":
            throw errorWithLibrary(`${result.type} record not allowed in index section`);
          case "Unknown":
            break;
        }
      }
      if (indexReader.bytesRemaining() !== 0) {
        throw errorWithLibrary(`${indexReader.bytesRemaining()} bytes remaining in index section`);
      }
      return new _McapIndexedReader({
        readable,
        chunkIndexes,
        attachmentIndexes,
        metadataIndexes,
        statistics,
        decompressHandlers,
        channelsById,
        schemasById,
        summaryOffsetsByOpcode,
        header,
        footer,
        dataEndOffset,
        dataSectionCrc,
        messageIndexCacheSizeBytes
      });
    }
    async *readMessages(args = {}) {
      const { topics, startTime = __privateGet(this, _messageStartTime), endTime = __privateGet(this, _messageEndTime), reverse = false, validateCrcs } = args;
      if (startTime == void 0 || endTime == void 0) {
        return;
      }
      let relevantChannels;
      if (topics) {
        relevantChannels = /* @__PURE__ */ new Set();
        for (const channel of this.channelsById.values()) {
          if (topics.includes(channel.topic)) {
            relevantChannels.add(channel.id);
          }
        }
      }
      const chunkCursors = new Heap((a, b) => a.compare(b));
      let chunksOrdered = true;
      let prevChunkEndTime;
      const readFullMessageIndexRange = __privateGet(this, _messageIndexReadable) !== __privateGet(this, _readable2);
      for (const chunkIndex of this.chunkIndexes) {
        if (chunkIndex.messageStartTime <= endTime && chunkIndex.messageEndTime >= startTime) {
          chunkCursors.push(new ChunkCursor({
            chunkIndex,
            relevantChannels,
            startTime,
            endTime,
            reverse,
            readFullMessageIndexRange
          }));
          if (chunksOrdered && prevChunkEndTime != void 0) {
            chunksOrdered = chunkIndex.messageStartTime >= prevChunkEndTime;
          }
          prevChunkEndTime = chunkIndex.messageEndTime;
        }
      }
      const chunkViewCache = /* @__PURE__ */ new Map();
      const chunkReader = new Reader(new DataView(new ArrayBuffer(0)));
      for (let cursor; cursor = chunkCursors.peek(); ) {
        if (!cursor.hasMessageIndexes()) {
          await cursor.loadMessageIndexes(__privateGet(this, _messageIndexReadable));
          if (cursor.hasMoreMessages()) {
            chunkCursors.replace(cursor);
          } else {
            chunkCursors.pop();
          }
          continue;
        }
        let chunkView = chunkViewCache.get(cursor.chunkIndex.chunkStartOffset);
        if (!chunkView) {
          chunkView = await __privateMethod(this, _McapIndexedReader_instances, loadChunkData_fn).call(this, cursor.chunkIndex, {
            validateCrcs: validateCrcs ?? true
          });
          chunkViewCache.set(cursor.chunkIndex.chunkStartOffset, chunkView);
        }
        const [logTime, offset] = cursor.popMessage();
        if (offset >= BigInt(chunkView.byteLength)) {
          throw __privateMethod(this, _McapIndexedReader_instances, errorWithLibrary_fn).call(this, `Message offset beyond chunk bounds (log time ${logTime}, offset ${offset}, chunk data length ${chunkView.byteLength}) in chunk at offset ${cursor.chunkIndex.chunkStartOffset}`);
        }
        chunkReader.reset(chunkView, Number(offset));
        const record = parseRecord(chunkReader, validateCrcs ?? true);
        if (!record) {
          throw __privateMethod(this, _McapIndexedReader_instances, errorWithLibrary_fn).call(this, `Unable to parse record at offset ${offset} in chunk at offset ${cursor.chunkIndex.chunkStartOffset}`);
        }
        if (record.type !== "Message") {
          throw __privateMethod(this, _McapIndexedReader_instances, errorWithLibrary_fn).call(this, `Unexpected record type ${record.type} in message index (time ${logTime}, offset ${offset} in chunk at offset ${cursor.chunkIndex.chunkStartOffset})`);
        }
        if (record.logTime !== logTime) {
          throw __privateMethod(this, _McapIndexedReader_instances, errorWithLibrary_fn).call(this, `Message log time ${record.logTime} did not match message index entry (${logTime} at offset ${offset} in chunk at offset ${cursor.chunkIndex.chunkStartOffset})`);
        }
        yield record;
        if (cursor.hasMoreMessages()) {
          if (!chunksOrdered) {
            chunkCursors.replace(cursor);
          }
        } else {
          chunkCursors.pop();
          chunkViewCache.delete(cursor.chunkIndex.chunkStartOffset);
        }
      }
    }
    async *readMetadata(args = {}) {
      const { name } = args;
      for (const metadataIndex of this.metadataIndexes) {
        if (name != void 0 && metadataIndex.name !== name) {
          continue;
        }
        const metadataData = await __privateGet(this, _readable2).read(metadataIndex.offset, metadataIndex.length);
        const metadataReader = new Reader(new DataView(metadataData.buffer, metadataData.byteOffset, metadataData.byteLength));
        const metadataRecord = parseRecord(metadataReader, false);
        if (metadataRecord?.type !== "Metadata") {
          throw __privateMethod(this, _McapIndexedReader_instances, errorWithLibrary_fn).call(this, `Metadata data at offset ${metadataIndex.offset} does not point to metadata record (found ${String(metadataRecord?.type)})`);
        }
        yield metadataRecord;
      }
    }
    async *readAttachments(args = {}) {
      const { name, mediaType, startTime = __privateGet(this, _attachmentStartTime), endTime = __privateGet(this, _attachmentEndTime), validateCrcs } = args;
      if (startTime == void 0 || endTime == void 0) {
        return;
      }
      for (const attachmentIndex of this.attachmentIndexes) {
        if (name != void 0 && attachmentIndex.name !== name) {
          continue;
        }
        if (mediaType != void 0 && attachmentIndex.mediaType !== mediaType) {
          continue;
        }
        if (attachmentIndex.logTime > endTime || attachmentIndex.logTime < startTime) {
          continue;
        }
        const attachmentData = await __privateGet(this, _readable2).read(attachmentIndex.offset, attachmentIndex.length);
        const attachmentReader = new Reader(new DataView(attachmentData.buffer, attachmentData.byteOffset, attachmentData.byteLength));
        const attachmentRecord = parseRecord(attachmentReader, validateCrcs ?? true);
        if (attachmentRecord?.type !== "Attachment") {
          throw __privateMethod(this, _McapIndexedReader_instances, errorWithLibrary_fn).call(this, `Attachment data at offset ${attachmentIndex.offset} does not point to attachment record (found ${String(attachmentRecord?.type)})`);
        }
        yield attachmentRecord;
      }
    }
  };
  _readable2 = new WeakMap();
  _messageIndexReadable = new WeakMap();
  _decompressHandlers = new WeakMap();
  _messageStartTime = new WeakMap();
  _messageEndTime = new WeakMap();
  _attachmentStartTime = new WeakMap();
  _attachmentEndTime = new WeakMap();
  _McapIndexedReader_instances = new WeakSet();
  errorWithLibrary_fn = function(message) {
    return new Error(`${message} [library=${this.header.library}]`);
  };
  loadChunkData_fn = async function(chunkIndex, options) {
    const chunkData = await __privateGet(this, _readable2).read(chunkIndex.chunkStartOffset, chunkIndex.chunkLength);
    const chunkReader = new Reader(new DataView(chunkData.buffer, chunkData.byteOffset, chunkData.byteLength));
    const chunkRecord = parseRecord(chunkReader, options?.validateCrcs ?? true);
    if (chunkRecord?.type !== "Chunk") {
      throw __privateMethod(this, _McapIndexedReader_instances, errorWithLibrary_fn).call(this, `Chunk start offset ${chunkIndex.chunkStartOffset} does not point to chunk record (found ${String(chunkRecord?.type)})`);
    }
    const chunk = chunkRecord;
    let buffer = chunk.records;
    if (chunk.compression !== "" && buffer.byteLength > 0) {
      const decompress = __privateGet(this, _decompressHandlers)?.[chunk.compression];
      if (!decompress) {
        throw __privateMethod(this, _McapIndexedReader_instances, errorWithLibrary_fn).call(this, `Unsupported compression ${chunk.compression}`);
      }
      buffer = decompress(buffer, chunk.uncompressedSize);
    }
    if (chunk.uncompressedCrc !== 0 && options?.validateCrcs !== false) {
      const chunkCrc = crc32(buffer);
      if (chunkCrc !== chunk.uncompressedCrc) {
        throw __privateMethod(this, _McapIndexedReader_instances, errorWithLibrary_fn).call(this, `Incorrect chunk CRC ${chunkCrc} (expected ${chunk.uncompressedCrc})`);
      }
    }
    return new DataView(buffer.buffer, buffer.byteOffset, buffer.byteLength);
  };
  var McapIndexedReader = _McapIndexedReader;

  // node_modules/@mcap/browser/dist/esm/BlobReadable.js
  var _blob;
  var BlobReadable = class {
    constructor(blob) {
      __privateAdd(this, _blob);
      __privateSet(this, _blob, blob);
    }
    async size() {
      return BigInt(__privateGet(this, _blob).size);
    }
    async read(offset, size) {
      if (offset + size > __privateGet(this, _blob).size) {
        throw new Error(`Read of ${size} bytes at offset ${offset} exceeds file size ${__privateGet(this, _blob).size}`);
      }
      return new Uint8Array(await __privateGet(this, _blob).slice(Number(offset), Number(offset + size)).arrayBuffer());
    }
  };
  _blob = new WeakMap();
  return __toCommonJS(mcap_vendor_entry_exports);
})();
