package panel

import (
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	"gorm.io/gorm"
	"gorm.io/gorm/clause"

	"github.com/mhsanaei/3x-ui/v3/internal/database"
	"github.com/mhsanaei/3x-ui/v3/internal/database/model"
	"github.com/mhsanaei/3x-ui/v3/internal/logger"
	"github.com/mhsanaei/3x-ui/v3/internal/util/crypto"
	ldaputil "github.com/mhsanaei/3x-ui/v3/internal/util/ldap"
	"github.com/mhsanaei/3x-ui/v3/internal/util/totp"
	"github.com/mhsanaei/3x-ui/v3/internal/web/service"
)

// UserService provides business logic for user management and authentication.
// It handles user creation, login, password management, and 2FA operations.
type UserService struct {
	settingService service.SettingService
}

// GetFirstUser retrieves the first user from the database.
// This is typically used for initial setup or when there's only one admin user.
func (s *UserService) GetFirstUser() (*model.User, error) {
	db := database.GetDB()

	user := &model.User{}
	err := db.Model(model.User{}).
		First(user).
		Error
	if err != nil {
		return nil, err
	}
	return user, nil
}

// HasDefaultCredential reports that nobody has chosen the login yet: a database
// holds no user before the first start, and an older one may still hold admin/admin.
func (s *UserService) HasDefaultCredential() (bool, error) {
	user, err := s.GetFirstUser()
	if database.IsNotFound(err) {
		return true, nil
	}
	if err != nil {
		return false, err
	}
	return user.Username == "admin" && crypto.CheckPasswordHash(user.Password, "admin"), nil
}

func (s *UserService) CheckUser(username string, password string, twoFactorCode string) (*model.User, error) {
	db := database.GetDB()

	user := &model.User{}

	err := db.Model(model.User{}).
		Where("username = ?", username).
		First(user).
		Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, errors.New("invalid credentials")
	} else if err != nil {
		logger.Warning("check user err:", err)
		return nil, err
	}

	if !crypto.CheckPasswordHash(user.Password, password) {
		ldapEnabled, _ := s.settingService.GetLdapEnable()
		if !ldapEnabled {
			return nil, errors.New("invalid credentials")
		}

		host, _ := s.settingService.GetLdapHost()
		port, _ := s.settingService.GetLdapPort()
		useTLS, _ := s.settingService.GetLdapUseTLS()
		skipVerify, _ := s.settingService.GetLdapInsecureSkipVerify()
		bindDN, _ := s.settingService.GetLdapBindDN()
		ldapPass, _ := s.settingService.GetLdapPassword()
		baseDN, _ := s.settingService.GetLdapBaseDN()
		userFilter, _ := s.settingService.GetLdapUserFilter()
		userAttr, _ := s.settingService.GetLdapUserAttr()

		cfg := ldaputil.Config{
			Host:               host,
			Port:               port,
			UseTLS:             useTLS,
			InsecureSkipVerify: skipVerify,
			BindDN:             bindDN,
			Password:           ldapPass,
			BaseDN:             baseDN,
			UserFilter:         userFilter,
			UserAttr:           userAttr,
		}
		ok, err := ldaputil.AuthenticateUser(cfg, username, password)
		if err != nil || !ok {
			return nil, errors.New("invalid credentials")
		}
	}

	twoFactorEnable, err := s.settingService.GetTwoFactorEnable()
	if err != nil {
		logger.Warning("check two factor err:", err)
		return nil, err
	}

	if twoFactorEnable {
		twoFactorToken, err := s.settingService.GetTwoFactorToken()
		if err != nil {
			logger.Warning("check two factor token err:", err)
			return nil, err
		}

		if !totp.VerifyWithSkew(twoFactorToken, twoFactorCode, time.Now()) {
			return nil, errors.New("invalid 2fa code")
		}
	}

	return user, nil
}

func (s *UserService) BumpLoginEpoch() error {
	db := database.GetDB()
	return db.Model(model.User{}).
		Where("1 = 1").
		Update("login_epoch", gorm.Expr("login_epoch + 1")).
		Error
}

func (s *UserService) UpdateUser(id int, expectedEpoch int64, username string, password string, twoFactorCode string) error {
	if len(username) > MaxUsernameLength {
		return fmt.Errorf("username can not be longer than %d bytes", MaxUsernameLength)
	}
	db := database.GetDB()
	hashedPassword, err := crypto.HashPasswordAsBcrypt(password)
	if err != nil {
		return err
	}

	return db.Transaction(func(tx *gorm.DB) error {
		result := tx.Model(&model.User{}).
			Where("id = ? AND COALESCE(login_epoch, 0) = ?", id, expectedEpoch).
			Updates(map[string]any{
				"username":    username,
				"password":    hashedPassword,
				"login_epoch": gorm.Expr("COALESCE(login_epoch, 0) + 1"),
			})
		if result.Error != nil {
			return result.Error
		}
		if result.RowsAffected != 1 {
			return errors.New("panel credentials changed concurrently; sign in again")
		}
		// Verify two-factor against the settings this transaction would reset.
		// The user update holds SQLite's write lock; PostgreSQL also locks these
		// settings rows while the code is verified and the reset is committed.
		var settings []model.Setting
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).
			Where("key IN ?", []string{"twoFactorEnable", "twoFactorToken"}).
			Order("id ASC").Find(&settings).Error; err != nil {
			return err
		}
		values := make(map[string]string, len(settings))
		for _, setting := range settings {
			if _, exists := values[setting.Key]; !exists {
				values[setting.Key] = setting.Value
			}
		}
		enabled := values["twoFactorEnable"]
		if enabled == "" {
			return nil
		}
		twoFactorEnable, err := strconv.ParseBool(enabled)
		if err != nil {
			return err
		}
		if !twoFactorEnable {
			return nil
		}
		if !totp.VerifyWithSkew(values["twoFactorToken"], strings.TrimSpace(twoFactorCode), time.Now()) {
			return errors.New("invalid two factor code")
		}
		// Preserve the existing 2FA reset behavior, but commit it together
		// with the credential change. A stale request must reset nothing.
		if err := tx.Model(&model.Setting{}).Where("key = ?", "twoFactorEnable").Update("value", "false").Error; err != nil {
			return err
		}
		return tx.Model(&model.Setting{}).Where("key = ?", "twoFactorToken").Update("value", "").Error
	})
}

func (s *UserService) UpdateFirstUser(username string, password string) error {
	if username == "" {
		return errors.New("username can not be empty")
	} else if len(username) > MaxUsernameLength {
		return fmt.Errorf("username can not be longer than %d bytes", MaxUsernameLength)
	} else if password == "" {
		return errors.New("password can not be empty")
	}
	hashedPassword, er := crypto.HashPasswordAsBcrypt(password)

	if er != nil {
		return er
	}

	db := database.GetDB()
	user := &model.User{}
	err := db.Model(model.User{}).First(user).Error
	if database.IsNotFound(err) {
		user.Username = username
		user.Password = hashedPassword
		return db.Model(model.User{}).Create(user).Error
	} else if err != nil {
		return err
	}
	user.Username = username
	user.Password = hashedPassword
	user.LoginEpoch++
	return db.Save(user).Error
}

// MaxUsernameLength bounds a panel username: the login route refuses longer names before
// logging or recording them, so no stored name may exceed it.
const MaxUsernameLength = 256
