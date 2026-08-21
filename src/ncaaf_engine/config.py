from pydantic import BaseModel, ConfigDict, Field, model_validator


class PublicCrowdingConfig(BaseModel):
    season_weight: float = 0.40
    recent_weight: float = 0.35
    concentration_weight: float = 0.25

    @model_validator(mode="after")
    def weights_sum_to_one(self):
        total = self.season_weight + self.recent_weight + self.concentration_weight
        if abs(total - 1.0) > 1e-9:
            raise ValueError("public crowding weights must sum to 1.0")
        return self


class AmmConfig(BaseModel):
    kind: str = "LMSR_BINARY"
    liquidity_b: float = Field(default=1000.0, gt=0)
    trade_fee_bps: int = Field(default=0, ge=0)


class RetailCrowdConfig(BaseModel):
    enabled: bool = True
    activation_threshold: float = Field(default=0.10, ge=0, le=1)
    base_quantity: float = Field(default=25.0, gt=0)
    exponent: float = Field(default=1.0, gt=0)


class MomentumRetailConfig(BaseModel):
    enabled: bool = True
    activation_threshold: float = Field(default=0.15, ge=0, le=1)
    base_quantity: float = Field(default=20.0, gt=0)


class ContrarianConfig(BaseModel):
    enabled: bool = True
    minimum_absolute_edge: float = Field(default=0.03, ge=0, lt=1)
    base_quantity: float = Field(default=20.0, gt=0)


class SharpFollowerConfig(BaseModel):
    totals_enabled: bool = True
    ats_enabled: bool = False
    belief_adjustment_enabled: bool = False


class RiskLimits(BaseModel):
    maximum_single_order_quantity: float = Field(default=100.0, gt=0)
    maximum_participant_contract_quantity: float = Field(default=500.0, gt=0)


class SettlementConfig(BaseModel):
    completion_window_hours: int = Field(default=72, gt=0)


class FeatureFlags(BaseModel):
    independent_power_model: bool = False
    historical_line_movement: bool = False
    multi_book_pricing: bool = False
    sharp_belief_adjustment: bool = False


class EngineConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    specification_version: str = "0.1.0"
    initial_belief_probability: float = Field(default=0.50, gt=0, lt=1)
    public_crowding: PublicCrowdingConfig = PublicCrowdingConfig()
    amm: AmmConfig = AmmConfig()
    retail_crowd: RetailCrowdConfig = RetailCrowdConfig()
    momentum_retail: MomentumRetailConfig = MomentumRetailConfig()
    contrarian: ContrarianConfig = ContrarianConfig()
    sharp_followers: SharpFollowerConfig = SharpFollowerConfig()
    risk_limits: RiskLimits = RiskLimits()
    settlement: SettlementConfig = SettlementConfig()
    feature_flags: FeatureFlags = FeatureFlags()
    totals_weights: dict[str, float] = {
        "mollydog": 1.00,
        "Insiderone777": 0.99,
        "courtney1966": 0.82,
        "BammBamm64": 0.76,
    }


DEFAULT_CONFIG = EngineConfig()
